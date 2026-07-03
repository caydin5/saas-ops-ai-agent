"""
Data schemas for the SaaS Ops AI Agent.

This file defines the structure of the data that moves through the API:
- what the user sends
- what the planner returns
- what the executor receives
- what the executor returns

Using Pydantic keeps the API predictable and validates inputs/outputs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# The possible business intentions the system can currently recognize.
Intent = Literal[
    "create_workspace",
    "generate_usage_report",
    "search_documentation",
    "unknown",
]

# The mock tools the system can currently execute.
ToolName = Literal[
    "create_workspace",
    "generate_usage_report",
    "search_documentation",
    "none",
]


class PlanRequest(BaseModel):
    """
    Request body for the /plan endpoint.

    Example:
    {
        "request": "Create a workspace for Acme Corp"
    }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request": "Create a workspace for Acme Corp",
            }
        }
    )

    request: str = Field(..., min_length=3)


class ActionPlan(BaseModel):
    """
    Structured action plan created from a natural-language request.

    This is the key AI-agent pattern:
    natural language gets converted into a predictable machine-readable plan.
    """

    intent: Intent
    tool_name: ToolName
    arguments: dict[str, Any]
    missing_information: list[str]
    requires_confirmation: bool
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExecuteRequest(BaseModel):
    """
    Request body for the /execute endpoint.

    The executor receives an ActionPlan and attempts to run the selected tool.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan": {
                    "intent": "create_workspace",
                    "tool_name": "create_workspace",
                    "arguments": {"customer_name": "Acme Corp"},
                    "missing_information": [],
                    "requires_confirmation": False,
                    "confidence": 0.86,
                }
            }
        }
    )

    plan: ActionPlan


class ExecuteResponse(BaseModel):
    """
    Response returned after attempting to execute an action plan.

    action_log is included to make the system auditable and easy to debug.
    """

    status: Literal["success", "error"]
    message: str
    action_log: list[str]
    result: dict[str, Any] = Field(default_factory=dict)