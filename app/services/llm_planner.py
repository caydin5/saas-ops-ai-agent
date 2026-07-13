"""
LLM-backed planner for the SaaS Ops AI Agent.

Uses OpenAI structured outputs to convert a natural-language request
into a validated ActionPlan. The model returns JSON that maps directly
to the existing Pydantic schema.

This module is selected when PLANNER_MODE=llm. When the API key is
missing, the endpoint returns a 503. When an API call fails at runtime,
the /plan handler falls back to the rule-based planner.
"""

from __future__ import annotations

import json
import logging
import os

from openai import APIError, AuthenticationError, OpenAI

from app.schemas import ActionPlan

logger = logging.getLogger(__name__)

# JSON schema that the LLM must conform to via structured output.
# Mirrors ActionPlan, minus planner_mode (injected after the call).
#
# OpenAI strict mode requires additionalProperties: false on every object
# and all properties must be listed in required. Unused fields are set to
# null by the model, then stripped in post-processing.
_ACTION_PLAN_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "action_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "create_workspace",
                        "generate_usage_report",
                        "search_documentation",
                        "unknown",
                    ],
                },
                "tool_name": {
                    "type": "string",
                    "enum": [
                        "create_workspace",
                        "generate_usage_report",
                        "search_documentation",
                        "none",
                    ],
                },
                "arguments": {
                    "type": "object",
                    "properties": {
                        "customer_name": {"type": ["string", "null"]},
                        "query": {"type": ["string", "null"]},
                        "period": {"type": ["string", "null"]},
                    },
                    "required": ["customer_name", "query", "period"],
                    "additionalProperties": False,
                },
                "missing_information": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "requires_confirmation": {"type": "boolean"},
                "confidence": {"type": "number"},
            },
            "required": [
                "intent",
                "tool_name",
                "arguments",
                "missing_information",
                "requires_confirmation",
                "confidence",
            ],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = """\
You are a SaaS operations assistant. Your job is to convert a user's \
natural-language request into a structured action plan.

Available tools:

1. create_workspace
   - Required argument: customer_name (string)
   - Use when the user wants to create a new workspace for a customer.

2. generate_usage_report
   - Required arguments: customer_name (string), period (string, default "last month")
   - Use when the user wants a usage report for a customer.

3. search_documentation
   - Required argument: query (string)
   - Use when the user wants to search product documentation.

Rules:
- Set intent and tool_name to the matching tool, or "unknown"/"none" if unclear.
- Extract arguments from the request. Set arguments you can extract to their \
value and set arguments that do not apply to null.
- If a required argument is missing from the request, set it to null and \
add it to missing_information.
- Set requires_confirmation to true for destructive or irreversible actions.
- Set confidence between 0.0 and 1.0 based on how clear the request is.\
"""


class MissingAPIKeyError(Exception):
    """Raised when the OpenAI API key is not configured."""


def _get_client() -> OpenAI:
    """Create an OpenAI client, raising MissingAPIKeyError if no key."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY is required when PLANNER_MODE=llm. "
            "Set it in .env or as an environment variable."
        )
    return OpenAI(api_key=api_key)


def _strip_null_arguments(arguments: dict) -> dict:
    """Remove null-valued keys from the arguments dict.

    The structured output schema uses nullable fields for all possible
    arguments. The model sets unused fields to null. This strips them
    so the resulting ActionPlan.arguments only contains actual values.
    """

    return {k: v for k, v in arguments.items() if v is not None}


def llm_plan_request(user_request: str) -> ActionPlan:
    """
    Convert a natural-language request into an ActionPlan using OpenAI.

    Uses structured outputs so the response is guaranteed to conform
    to the ActionPlan JSON schema.

    Args:
        user_request: The user's natural-language request.

    Returns:
        A structured ActionPlan with planner_mode="llm".

    Raises:
        MissingAPIKeyError: If OPENAI_API_KEY is not set.
        openai.APIError: If the OpenAI API call fails.
    """

    client = _get_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    logger.info("LLM planner: sending request to %s", model)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_request},
        ],
        response_format=_ACTION_PLAN_SCHEMA,
        temperature=0.0,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    # Strip null argument values (unused fields from the fixed schema).
    data["arguments"] = _strip_null_arguments(data.get("arguments", {}))

    # Clamp confidence to [0.0, 1.0] in case the model returns out-of-range.
    data["confidence"] = max(0.0, min(1.0, data.get("confidence", 0.5)))
    data["planner_mode"] = "llm"

    plan = ActionPlan(**data)
    logger.info("LLM planner: intent=%s tool=%s confidence=%.2f",
                plan.intent, plan.tool_name, plan.confidence)

    return plan
