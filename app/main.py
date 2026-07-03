"""
FastAPI entry point for the SaaS Ops AI Agent.

This file exposes the HTTP API endpoints:
- GET /health
- POST /plan
- POST /execute

The business logic lives in app/services/planner.py.
Keeping the API layer thin makes the project easier to maintain and test.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas import ActionPlan, ExecuteRequest, ExecuteResponse, PlanRequest
from app.services.planner import execute_plan, plan_request

# Basic logging setup for local development.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SaaS Ops AI Agent",
    description="A workflow orchestrator that converts natural-language SaaS operations requests into structured action plans.",
    version="0.1.0",
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

    This endpoint does not execute anything.
    It only returns the structured plan.
    """

    return plan_request(payload.request)


@app.post("/execute", response_model=ExecuteResponse)
def execute(payload: ExecuteRequest) -> ExecuteResponse:
    """
    Execute a previously created action plan.

    This endpoint receives an ActionPlan and runs the selected mock tool.
    """

    return execute_plan(payload.plan)