"""
API tests for the SaaS Ops AI Agent.

These tests verify that the FastAPI endpoints work end-to-end:
- /health confirms the API is running
- /plan converts natural language into a structured action plan
- /plan validates input (rejects empty or too-short requests)
- /execute runs a valid action plan
- /execute safely rejects plans with missing information
- /execute safely rejects crafted payloads with missing arguments
- /execute blocks confirmation-required and mismatched plans
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """
    The health endpoint should confirm the API is running.
    """

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_plan_endpoint_create_workspace():
    """
    The /plan endpoint should convert a natural-language request
    into a structured create_workspace action plan.
    """

    response = client.post(
        "/plan",
        json={"request": "Create a workspace for Acme Corp"},
    )

    data = response.json()

    assert response.status_code == 200
    assert data["intent"] == "create_workspace"
    assert data["tool_name"] == "create_workspace"
    assert data["arguments"]["customer_name"] == "Acme Corp"
    assert data["missing_information"] == []


def test_execute_endpoint_create_workspace():
    """
    The /execute endpoint should execute a valid create_workspace plan.
    """

    plan_response = client.post(
        "/plan",
        json={"request": "Create a workspace for Acme Corp"},
    )

    plan = plan_response.json()

    execute_response = client.post(
        "/execute",
        json={"plan": plan},
    )

    data = execute_response.json()

    assert execute_response.status_code == 200
    assert data["status"] == "success"
    assert data["result"]["customer_name"] == "Acme Corp"
    assert data["result"]["created"] is True


def test_execute_endpoint_rejects_missing_information():
    """
    The /execute endpoint should not execute a plan when required
    information is missing.
    """

    plan_response = client.post(
        "/plan",
        json={"request": "Create a workspace"},
    )

    plan = plan_response.json()

    execute_response = client.post(
        "/execute",
        json={"plan": plan},
    )

    data = execute_response.json()

    assert execute_response.status_code == 200
    assert data["status"] == "error"
    assert "customer_name" in data["action_log"][1]


def test_plan_endpoint_rejects_empty_request():
    """
    The /plan endpoint should return 422 for an empty request body.
    """

    response = client.post("/plan", json={})

    assert response.status_code == 422


def test_plan_endpoint_rejects_short_request():
    """
    The /plan endpoint should return 422 for a request shorter than
    the min_length=3 validation on PlanRequest.
    """

    response = client.post("/plan", json={"request": "Hi"})

    assert response.status_code == 422


def test_execute_endpoint_usage_report():
    """
    The /execute endpoint should execute a valid generate_usage_report plan.
    """

    plan_response = client.post(
        "/plan",
        json={"request": "Generate a usage report for Beta Corp"},
    )

    plan = plan_response.json()

    execute_response = client.post(
        "/execute",
        json={"plan": plan},
    )

    data = execute_response.json()

    assert execute_response.status_code == 200
    assert data["status"] == "success"
    assert data["result"]["customer_name"] == "Beta Corp"
    assert data["result"]["report_ready"] is True


def test_execute_endpoint_search_documentation():
    """
    The /execute endpoint should execute a valid search_documentation plan.
    """

    plan_response = client.post(
        "/plan",
        json={"request": "Search documentation for workspace API"},
    )

    plan = plan_response.json()

    execute_response = client.post(
        "/execute",
        json={"plan": plan},
    )

    data = execute_response.json()

    assert execute_response.status_code == 200
    assert data["status"] == "success"
    assert "matches" in data["result"]


def test_execute_endpoint_rejects_crafted_payload():
    """
    If a crafted plan is sent directly to /execute with tool_name set
    but arguments empty, the endpoint should return an error —
    not crash with a 500.
    """

    crafted_plan = {
        "intent": "create_workspace",
        "tool_name": "create_workspace",
        "arguments": {},
        "missing_information": [],
        "requires_confirmation": False,
        "confidence": 0.9,
    }

    response = client.post("/execute", json={"plan": crafted_plan})

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "error"
    assert "customer_name" in data["message"]


def test_execute_endpoint_blocks_confirmation_required():
    """
    If requires_confirmation is True, the /execute endpoint
    should refuse to run and return an error through HTTP.
    """

    crafted_plan = {
        "intent": "create_workspace",
        "tool_name": "create_workspace",
        "arguments": {"customer_name": "Acme Corp"},
        "missing_information": [],
        "requires_confirmation": True,
        "confidence": 0.9,
    }

    response = client.post("/execute", json={"plan": crafted_plan})

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "error"
    assert "confirmation" in data["message"].lower()


def test_execute_endpoint_rejects_mismatched_intent_tool():
    """
    If intent and tool_name are inconsistent, the /execute endpoint
    should reject the plan.
    """

    crafted_plan = {
        "intent": "create_workspace",
        "tool_name": "search_documentation",
        "arguments": {"query": "anything"},
        "missing_information": [],
        "requires_confirmation": False,
        "confidence": 0.9,
    }

    response = client.post("/execute", json={"plan": crafted_plan})

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "error"


def test_execute_endpoint_rejects_null_argument_value():
    """
    If a required argument is present but null, the /execute endpoint
    should reject it — not crash with a 500.
    """

    crafted_plan = {
        "intent": "create_workspace",
        "tool_name": "create_workspace",
        "arguments": {"customer_name": None},
        "missing_information": [],
        "requires_confirmation": False,
        "confidence": 0.9,
    }

    response = client.post("/execute", json={"plan": crafted_plan})

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "error"
    assert "customer_name" in data["message"]