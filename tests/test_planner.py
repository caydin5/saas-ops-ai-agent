"""
Tests for the planner and executor logic.

These tests verify that:
- natural-language requests are converted into the right structured plans
- missing information is detected
- executable plans call the correct mock tools
- unknown requests are handled safely
- argument validation catches crafted payloads
- confirmation blocking prevents unconfirmed execution
- intent/tool_name mismatches are rejected
"""

from __future__ import annotations

from app.services.planner import execute_plan, plan_request
from app.schemas import ActionPlan


def test_plan_create_workspace_with_customer_name():
    """
    The planner should detect a workspace creation request
    and extract the customer name.
    """

    plan = plan_request("Create a workspace for Acme Corp")

    assert plan.intent == "create_workspace"
    assert plan.tool_name == "create_workspace"
    assert plan.arguments["customer_name"] == "Acme Corp"
    assert plan.missing_information == []
    assert plan.confidence > 0.8


def test_plan_create_workspace_missing_customer_name():
    """
    If the user asks to create a workspace but does not provide
    a customer name, the planner should flag missing information.
    """

    plan = plan_request("Create a new workspace")

    assert plan.intent == "create_workspace"
    assert plan.tool_name == "create_workspace"
    assert "customer_name" in plan.missing_information


def test_execute_create_workspace_success():
    """
    A valid create_workspace plan should execute successfully.
    """

    plan = plan_request("Create a workspace for Acme Corp")
    response = execute_plan(plan)

    assert response.status == "success"
    assert response.result["created"] is True
    assert response.result["customer_name"] == "Acme Corp"


def test_plan_usage_report():
    """
    The planner should detect a usage report request
    and extract the customer name.
    """

    plan = plan_request("Generate a usage report for Beta Corp")

    assert plan.intent == "generate_usage_report"
    assert plan.tool_name == "generate_usage_report"
    assert plan.arguments["customer_name"] == "Beta Corp"


def test_unknown_request():
    """
    Unknown requests should not be forced into a random tool.

    This is important for safe AI-agent behavior.
    """

    plan = plan_request("Tell me a joke")

    assert plan.intent == "unknown"
    assert plan.tool_name == "none"
    assert "intent" in plan.missing_information


def test_execute_usage_report_success():
    """
    A valid generate_usage_report plan should execute successfully
    and return expected report fields.
    """

    plan = plan_request("Generate a usage report for Beta Corp")
    response = execute_plan(plan)

    assert response.status == "success"
    assert response.result["customer_name"] == "Beta Corp"
    assert response.result["report_ready"] is True
    assert "api_calls" in response.result


def test_plan_search_documentation():
    """
    The planner should detect a documentation search request.
    """

    plan = plan_request("Search docs for workspace API")

    assert plan.intent == "search_documentation"
    assert plan.tool_name == "search_documentation"
    assert plan.arguments["query"] == "Search docs for workspace API"
    assert plan.missing_information == []


def test_execute_search_documentation_success():
    """
    A valid search_documentation plan should execute successfully
    and return matching documents.
    """

    plan = plan_request("Search docs for workspace API")
    response = execute_plan(plan)

    assert response.status == "success"
    assert "matches" in response.result
    assert len(response.result["matches"]) > 0


def test_execute_unknown_plan_returns_error():
    """
    Executing a plan with tool_name='none' should return an error,
    not crash or produce a success response.
    """

    plan = plan_request("Tell me a joke")
    response = execute_plan(plan)

    assert response.status == "error"


def test_execute_rejects_crafted_payload_missing_arguments():
    """
    If a crafted ActionPlan is sent directly to /execute with
    the right tool_name but missing required arguments, the executor
    should reject it instead of crashing with a KeyError.

    This protects against payloads that bypass the planner.
    """

    crafted_plan = ActionPlan(
        intent="create_workspace",
        tool_name="create_workspace",
        arguments={},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "customer_name" in response.message


def test_execute_rejects_crafted_report_missing_customer():
    """
    Same as above but for generate_usage_report — ensures the
    argument validation covers all tools, not just create_workspace.
    """

    crafted_plan = ActionPlan(
        intent="generate_usage_report",
        tool_name="generate_usage_report",
        arguments={"period": "last month"},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "customer_name" in response.message


def test_execute_blocks_when_confirmation_required():
    """
    If requires_confirmation is True, the executor should refuse
    to run the action and return a clear error message.
    """

    plan = ActionPlan(
        intent="create_workspace",
        tool_name="create_workspace",
        arguments={"customer_name": "Acme Corp"},
        missing_information=[],
        requires_confirmation=True,
        confidence=0.9,
    )

    response = execute_plan(plan)

    assert response.status == "error"
    assert "confirmation" in response.message.lower()


def test_execute_rejects_mismatched_intent_and_tool():
    """
    If a crafted payload sets intent='create_workspace' but
    tool_name='search_documentation', the executor should reject
    the inconsistent combination.
    """

    crafted_plan = ActionPlan(
        intent="create_workspace",
        tool_name="search_documentation",
        arguments={"query": "anything"},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "intent" in response.message.lower() or "combination" in response.message.lower()


def test_execute_rejects_null_customer_name():
    """
    If customer_name is present but null, the executor should
    reject it instead of passing None into the mock tool.
    """

    crafted_plan = ActionPlan(
        intent="create_workspace",
        tool_name="create_workspace",
        arguments={"customer_name": None},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "customer_name" in response.message


def test_execute_rejects_empty_string_customer_name():
    """
    If customer_name is an empty string, the executor should
    reject it rather than creating a workspace with no name.
    """

    crafted_plan = ActionPlan(
        intent="create_workspace",
        tool_name="create_workspace",
        arguments={"customer_name": ""},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "customer_name" in response.message


def test_plan_extracts_hyphenated_customer_name():
    """
    The planner should handle hyphenated customer names like Acme-Corp.
    """

    plan = plan_request("Create a workspace for Acme-Corp")

    assert plan.arguments.get("customer_name") == "Acme-Corp"
    assert plan.missing_information == []


def test_plan_extracts_short_uppercase_name():
    """
    The planner should handle short uppercase names like 3M.
    """

    plan = plan_request("Create a workspace for 3M")

    assert plan.arguments.get("customer_name") == "3M"
    assert plan.missing_information == []


def test_execute_rejects_wrong_type_customer_name():
    """
    If customer_name is an integer instead of a string,
    the executor should reject it — not crash with a 500.
    """

    crafted_plan = ActionPlan(
        intent="create_workspace",
        tool_name="create_workspace",
        arguments={"customer_name": 123},
        missing_information=[],
        requires_confirmation=False,
        confidence=0.9,
    )

    response = execute_plan(crafted_plan)

    assert response.status == "error"
    assert "customer_name" in response.message


def test_plan_stops_at_stop_word_and():
    """
    'Create a workspace for Acme Corp and notify admin' should
    extract 'Acme Corp', not 'Acme Corp and notify admin'.
    """

    plan = plan_request("Create a workspace for Acme Corp and notify admin")

    assert plan.arguments.get("customer_name") == "Acme Corp"


def test_plan_stops_at_stop_word_for():
    """
    'Generate a usage report for Beta Corp for last week' should
    extract 'Beta Corp', not 'Beta Corp for last week'.
    """

    plan = plan_request("Generate a usage report for Beta Corp for last week")

    assert plan.arguments.get("customer_name") == "Beta Corp"


def test_plan_stops_at_stop_word_needs():
    """
    'Customer Acme Corp needs a usage report' should
    extract 'Acme Corp', not 'Acme Corp needs a usage report'.
    """

    plan = plan_request("Customer Acme Corp needs a usage report")

    assert plan.arguments.get("customer_name") == "Acme Corp"