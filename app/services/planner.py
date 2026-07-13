"""
Planning and execution logic for the SaaS Ops AI Agent.

This file contains two main responsibilities:

1. Planning:
   Convert a natural-language request into a structured ActionPlan.

2. Execution:
   Take an ActionPlan and run the selected mock tool.

The planner mode is controlled by the PLANNER_MODE environment variable:
- "rule_based" (default): Uses regex-based intent detection.
- "llm": Uses OpenAI structured outputs for intent detection.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Callable

from app.schemas import ActionPlan, ExecuteResponse
from app.services.tools import (
    create_workspace,
    generate_usage_report,
    search_documentation,
)

logger = logging.getLogger(__name__)


def get_planner() -> Callable[[str], ActionPlan]:
    """Return the active planner function based on PLANNER_MODE.

    Returns:
        Either ``plan_request`` (rule-based) or ``llm_plan_request`` (LLM).
    """

    mode = os.getenv("PLANNER_MODE", "rule_based").lower()

    if mode == "llm":
        from app.services.llm_planner import llm_plan_request
        return llm_plan_request

    if mode != "rule_based":
        logger.warning(
            "Unrecognized PLANNER_MODE='%s'. Falling back to rule_based.",
            mode,
        )

    return plan_request


# Words that should stop the customer-name capture.
# Without these, "for Acme Corp and notify admin" would extract
# "Acme Corp and notify admin" instead of "Acme Corp".
_STOP_WORDS: set[str] = {
    "and", "or", "but", "for", "needs", "need", "with", "from",
    "using", "about", "tomorrow", "today", "yesterday", "last",
    "next", "please", "then", "also", "the", "this", "that",
}


def _extract_customer_name(text: str) -> str | None:
    """
    Extract a likely customer name from the user's request.

    This is a simple MVP implementation using regular expressions
    with stop-word boundary detection.

    It looks for patterns like:
    - "for Acme Corp"
    - "customer Acme Corp"
    - "for 3M"
    - "for Acme-Corp"

    Stop words (and, for, needs, etc.) terminate the name capture
    to prevent over-extraction.

    Args:
        text: The raw user request.

    Returns:
        The extracted customer name, or None if no customer name is found.
    """

    # Patterns match capitalized, hyphenated, alphanumeric, or short
    # uppercase names (e.g. "3M", "Acme-Corp", "Beta Corp").
    patterns = [
        r"(?i)for\s+([A-Z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+)*)",
        r"(?i)customer\s+([A-Z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+)*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw_name = match.group(1).strip()
            # Trim trailing stop words and any trailing punctuation.
            words = raw_name.split()
            trimmed: list[str] = []
            for word in words:
                if word.lower().rstrip(".,;:!?") in _STOP_WORDS:
                    break
                trimmed.append(word)
            if trimmed:
                return " ".join(trimmed).rstrip(".,;:!?")

    return None


def plan_request(user_request: str) -> ActionPlan:
    """
    Convert a natural-language SaaS operations request into an ActionPlan.

    This function is the "planner" part of the agent.

    Example:
        "Create a workspace for Acme Corp"

    Becomes:
        intent = "create_workspace"
        tool_name = "create_workspace"
        arguments = {"customer_name": "Acme Corp"}

    Args:
        user_request: The user's natural-language request.

    Returns:
        A structured ActionPlan that can later be executed.
    """

    normalized = user_request.lower()
    customer_name = _extract_customer_name(user_request)

    # Case 1: User wants to create a customer workspace.
    if "create" in normalized and "workspace" in normalized:
        missing = [] if customer_name else ["customer_name"]

        return ActionPlan(
            intent="create_workspace",
            tool_name="create_workspace",
            arguments={"customer_name": customer_name} if customer_name else {},
            missing_information=missing,
            requires_confirmation=False,
            confidence=0.86 if customer_name else 0.62,
        )

    # Case 2: User wants a usage report.
    if "usage" in normalized and "report" in normalized:
        missing = [] if customer_name else ["customer_name"]

        return ActionPlan(
            intent="generate_usage_report",
            tool_name="generate_usage_report",
            arguments={
                "customer_name": customer_name,
                "period": "last month",
            }
            if customer_name
            else {"period": "last month"},
            missing_information=missing,
            requires_confirmation=False,
            confidence=0.82 if customer_name else 0.58,
        )

    # Case 3: User wants to search documentation.
    if "search" in normalized or "documentation" in normalized or "docs" in normalized:
        return ActionPlan(
            intent="search_documentation",
            tool_name="search_documentation",
            arguments={"query": user_request},
            missing_information=[],
            requires_confirmation=False,
            confidence=0.78,
        )

    # Fallback case: the system does not understand the request.
    return ActionPlan(
        intent="unknown",
        tool_name="none",
        arguments={},
        missing_information=["intent"],
        requires_confirmation=False,
        confidence=0.25,
    )


# Maps each tool to the argument keys it requires.
_REQUIRED_ARGUMENTS: dict[str, list[str]] = {
    "create_workspace": ["customer_name"],
    "generate_usage_report": ["customer_name"],
    "search_documentation": ["query"],
}

# Valid combinations of intent and tool_name.
# Prevents crafted payloads from mixing unrelated intents and tools.
_VALID_INTENT_TOOL_PAIRS: set[tuple[str, str]] = {
    ("create_workspace", "create_workspace"),
    ("generate_usage_report", "generate_usage_report"),
    ("search_documentation", "search_documentation"),
    ("unknown", "none"),
}


def _validate_arguments(plan: ActionPlan) -> list[str]:
    """
    Check that the plan's arguments contain all required keys with non-empty values.

    This protects against crafted payloads sent directly to /execute that
    bypass the planner's own missing-information checks.

    Both missing keys and keys with null/empty values are rejected.

    Args:
        plan: The ActionPlan to validate.

    Returns:
        A list of invalid argument names. Empty if all required args are valid.
    """

    required = _REQUIRED_ARGUMENTS.get(plan.tool_name, [])
    invalid: list[str] = []

    for key in required:
        value = plan.arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            invalid.append(key)

    return invalid


def execute_plan(plan: ActionPlan) -> ExecuteResponse:
    """
    Execute a structured ActionPlan by calling the selected mock tool.

    This function represents the "action" part of the agent.

    The executor is intentionally separate from the planner:
    - /plan decides what should happen
    - /execute performs the action

    This separation makes the system safer and easier to audit.

    Args:
        plan: The structured ActionPlan created by the planner.

    Returns:
        An ExecuteResponse describing whether execution succeeded or failed.
    """

    logger.info("Executing plan: %s", plan.intent)

    # Block execution if the plan requires human confirmation.
    if plan.requires_confirmation:
        return ExecuteResponse(
            status="error",
            message="This action requires human confirmation before execution.",
            action_log=[
                "Received action plan",
                "Action requires confirmation",
                "Execution stopped — awaiting confirmation",
            ],
        )

    # Validate that intent and tool_name are a valid combination.
    # Prevents crafted payloads from mixing unrelated intents and tools.
    if (plan.intent, plan.tool_name) not in _VALID_INTENT_TOOL_PAIRS:
        return ExecuteResponse(
            status="error",
            message=f"Invalid intent/tool combination: {plan.intent}/{plan.tool_name}.",
            action_log=[
                "Received action plan",
                f"Intent '{plan.intent}' does not match tool '{plan.tool_name}'",
                "Execution stopped",
            ],
        )

    # Stop execution if the planner detected missing required information.
    if plan.missing_information:
        return ExecuteResponse(
            status="error",
            message="Cannot execute plan because required information is missing.",
            action_log=[
                "Received action plan",
                f"Missing information: {', '.join(plan.missing_information)}",
                "Execution stopped",
            ],
        )

    # Validate that all required arguments are present and non-empty.
    # This catches crafted payloads sent directly to /execute.
    missing_args = _validate_arguments(plan)
    if missing_args:
        return ExecuteResponse(
            status="error",
            message=f"Missing or empty required arguments: {', '.join(missing_args)}.",
            action_log=[
                "Received action plan",
                f"Argument validation failed: {', '.join(missing_args)}",
                "Execution stopped",
            ],
        )

    # Execute workspace creation.
    if plan.tool_name == "create_workspace":
        result = create_workspace(customer_name=plan.arguments["customer_name"])

        return ExecuteResponse(
            status="success",
            message=f"Workspace created for {plan.arguments['customer_name']}.",
            action_log=[
                "Received action plan",
                "Validated customer_name",
                "Selected create_workspace tool",
                "Executed mock workspace creation",
            ],
            result=result,
        )

    # Execute usage report generation.
    if plan.tool_name == "generate_usage_report":
        result = generate_usage_report(
            customer_name=plan.arguments["customer_name"],
            period=plan.arguments.get("period", "last month"),
        )

        return ExecuteResponse(
            status="success",
            message=f"Usage report generated for {plan.arguments['customer_name']}.",
            action_log=[
                "Received action plan",
                "Validated customer_name and period",
                "Selected generate_usage_report tool",
                "Executed mock usage report generation",
            ],
            result=result,
        )

    # Execute documentation search.
    if plan.tool_name == "search_documentation":
        result = search_documentation(query=plan.arguments["query"])

        return ExecuteResponse(
            status="success",
            message="Documentation search completed.",
            action_log=[
                "Received action plan",
                "Validated search query",
                "Selected search_documentation tool",
                "Executed mock documentation search",
            ],
            result=result,
        )

    # Fallback if no supported tool was selected.
    return ExecuteResponse(
        status="error",
        message="No executable tool was selected.",
        action_log=[
            "Received action plan",
            "No matching tool found",
            "Execution stopped",
        ],
    )