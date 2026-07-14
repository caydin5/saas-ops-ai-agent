"""
FastAPI entry point for the SaaS Ops AI Agent.

This file exposes the HTTP API endpoints:
- GET /health
- POST /plan
- POST /execute

The business logic lives in app/services/planner.py and
app/services/llm_planner.py. Keeping the API layer thin makes
the project easier to maintain and test.
"""

from __future__ import annotations

import json
import logging

import openai

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas import ActionPlan, ExecuteRequest, ExecuteResponse, PlanRequest
from app.services.llm_planner import MissingAPIKeyError
from app.services.planner import execute_plan, get_planner, plan_request

load_dotenv()

# Basic logging setup for local development.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SaaS Ops AI Agent",
    description="A workflow orchestrator that converts natural-language SaaS operations requests into structured action plans.",
    version="0.1.0",
)


@app.exception_handler(MissingAPIKeyError)
async def missing_api_key_handler(
    request: Request, exc: MissingAPIKeyError,
) -> JSONResponse:
    """Return 503 when LLM mode is selected but the API key is missing.

    This is a configuration error that cannot be resolved at runtime,
    so we return 503 (Service Unavailable) instead of falling back.
    """

    return JSONResponse(
        status_code=503,
        content={
            "status": "error",
            "message": str(exc),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    Returns a clean JSON error instead of a raw 500 traceback.
    This prevents leaking internal details and keeps responses consistent.
    """

    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal error occurred. Please check your request and try again.",
        },
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Useful for verifying that the API is running.
    In production, this could be used by monitoring or deployment systems.
    """

    return {"status": "ok"}


@app.post("/plan", response_model=ActionPlan)
def plan(payload: PlanRequest) -> ActionPlan:
    """
    Create an action plan from a natural-language request.

    Uses the planner selected by PLANNER_MODE (default: rule_based).
    When the LLM planner fails at runtime (API errors, timeouts), the
    endpoint falls back to the rule-based planner and logs the failure.
    MissingAPIKeyError is NOT caught here — it propagates to the
    dedicated 503 handler since it is a configuration error.
    """

    planner = get_planner()

    # If using the LLM planner, wrap the call with fallback.
    if planner is not plan_request:
        try:
            return planner(payload.request)
        except MissingAPIKeyError:
            raise  # propagate to 503 handler
        except (
            openai.APIError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.APITimeoutError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as exc:
            logger.warning(
                "LLM planner failed, falling back to rule-based: %s", exc,
            )
            result = plan_request(payload.request)
            result.planner_mode = "rule_based"
            return result

    return planner(payload.request)


@app.post("/execute", response_model=ExecuteResponse)
def execute(payload: ExecuteRequest) -> ExecuteResponse:
    """
    Execute a previously created action plan.

    This endpoint receives an ActionPlan and runs the selected mock tool.
    """

    return execute_plan(payload.plan)