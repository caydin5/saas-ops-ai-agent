"""Tests for the LLM-backed planner."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import openai
import pytest
from fastapi.testclient import TestClient

from app.services.llm_planner import MissingAPIKeyError, llm_plan_request


# --- Helpers ---

def _mock_openai_response(data: dict) -> MagicMock:
    """Build a mock that mimics openai.chat.completions.create(...)."""

    choice = MagicMock()
    choice.message.content = json.dumps(data)

    response = MagicMock()
    response.choices = [choice]
    return response


# These fixtures mirror what the real structured-output schema returns:
# all argument fields are present, unused ones set to null.

_WORKSPACE_PLAN = {
    "intent": "create_workspace",
    "tool_name": "create_workspace",
    "arguments": {"customer_name": "Acme Corp", "query": None, "period": None},
    "missing_information": [],
    "requires_confirmation": False,
    "confidence": 0.92,
}

_REPORT_PLAN = {
    "intent": "generate_usage_report",
    "tool_name": "generate_usage_report",
    "arguments": {"customer_name": "Beta Corp", "query": None, "period": "last month"},
    "missing_information": [],
    "requires_confirmation": False,
    "confidence": 0.88,
}

_SEARCH_PLAN = {
    "intent": "search_documentation",
    "tool_name": "search_documentation",
    "arguments": {"customer_name": None, "query": "workspace API", "period": None},
    "missing_information": [],
    "requires_confirmation": False,
    "confidence": 0.80,
}

_UNKNOWN_PLAN = {
    "intent": "unknown",
    "tool_name": "none",
    "arguments": {"customer_name": None, "query": None, "period": None},
    "missing_information": ["intent"],
    "requires_confirmation": False,
    "confidence": 0.20,
}

_MISSING_INFO_PLAN = {
    "intent": "create_workspace",
    "tool_name": "create_workspace",
    "arguments": {"customer_name": None, "query": None, "period": None},
    "missing_information": ["customer_name"],
    "requires_confirmation": False,
    "confidence": 0.55,
}


# --- Unit tests ---


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_create_workspace(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_WORKSPACE_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Create a workspace for Acme Corp")

    assert plan.intent == "create_workspace"
    assert plan.tool_name == "create_workspace"
    assert plan.arguments["customer_name"] == "Acme Corp"
    assert plan.planner_mode == "llm"
    assert plan.confidence == 0.92


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_strips_null_arguments(mock_openai_cls):
    """Null-valued argument fields should be stripped from the plan."""

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_WORKSPACE_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Create a workspace for Acme Corp")

    assert "query" not in plan.arguments
    assert "period" not in plan.arguments
    assert plan.arguments == {"customer_name": "Acme Corp"}


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_usage_report(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_REPORT_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Generate a usage report for Beta Corp")

    assert plan.intent == "generate_usage_report"
    assert plan.arguments == {"customer_name": "Beta Corp", "period": "last month"}
    assert plan.planner_mode == "llm"


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_search_docs(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_SEARCH_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Search docs for workspace API")

    assert plan.intent == "search_documentation"
    assert plan.arguments == {"query": "workspace API"}
    assert plan.planner_mode == "llm"


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_unknown_request(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_UNKNOWN_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Do something random")

    assert plan.intent == "unknown"
    assert plan.tool_name == "none"
    assert plan.arguments == {}
    assert plan.planner_mode == "llm"


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_detects_missing_info(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_MISSING_INFO_PLAN)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Create a workspace")

    assert plan.missing_information == ["customer_name"]
    assert plan.arguments == {}


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_clamps_high_confidence(mock_openai_cls):
    """Confidence > 1.0 from the model should be clamped to 1.0."""

    data = {**_WORKSPACE_PLAN, "confidence": 1.5}
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(data)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Create a workspace for Acme Corp")

    assert plan.confidence == 1.0


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_clamps_negative_confidence(mock_openai_cls):
    """Confidence < 0.0 from the model should be clamped to 0.0."""

    data = {**_WORKSPACE_PLAN, "confidence": -0.3}
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(data)
    mock_openai_cls.return_value = mock_client

    plan = llm_plan_request("Create a workspace for Acme Corp")

    assert plan.confidence == 0.0


@patch.dict(os.environ, {}, clear=True)
def test_llm_planner_raises_on_missing_api_key(monkeypatch):
    """Should raise MissingAPIKeyError when OPENAI_API_KEY is not set."""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY is required"):
        llm_plan_request("Create a workspace for Acme Corp")


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
@patch("app.services.llm_planner.OpenAI")
def test_llm_planner_uses_configured_model(mock_openai_cls, monkeypatch):
    """Should pass the OPENAI_MODEL env var to the API call."""

    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(_WORKSPACE_PLAN)
    mock_openai_cls.return_value = mock_client

    llm_plan_request("Create a workspace for Acme Corp")

    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o"


# --- Planner factory ---


def test_get_planner_defaults_to_rule_based(monkeypatch):
    """Default PLANNER_MODE should return the rule-based planner."""

    monkeypatch.delenv("PLANNER_MODE", raising=False)

    from app.services.planner import get_planner, plan_request
    planner = get_planner()

    assert planner is plan_request


def test_get_planner_selects_llm_mode(monkeypatch):
    """PLANNER_MODE=llm should return the LLM planner."""

    monkeypatch.setenv("PLANNER_MODE", "llm")

    from app.services.planner import get_planner
    from app.services.llm_planner import llm_plan_request
    planner = get_planner()

    assert planner is llm_plan_request


def test_get_planner_warns_on_invalid_mode(monkeypatch, caplog):
    """Invalid PLANNER_MODE should log a warning and select rule-based."""

    monkeypatch.setenv("PLANNER_MODE", "invalid_mode")

    import logging
    with caplog.at_level(logging.WARNING):
        from app.services.planner import get_planner, plan_request
        planner = get_planner()

    assert planner is plan_request
    assert "Unrecognized PLANNER_MODE" in caplog.text


# --- API-level fallback and 503 tests ---


def test_plan_endpoint_returns_503_on_missing_api_key(monkeypatch):
    """PLANNER_MODE=llm without OPENAI_API_KEY should return 503."""

    monkeypatch.setenv("PLANNER_MODE", "llm")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/plan", json={"request": "Create a workspace for Acme Corp"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["message"]


@patch("app.services.llm_planner.OpenAI")
def test_plan_endpoint_falls_back_on_api_error(mock_openai_cls, monkeypatch):
    """LLM API errors should fall back to rule-based planner."""

    monkeypatch.setenv("PLANNER_MODE", "llm")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=MagicMock(),
    )
    mock_openai_cls.return_value = mock_client

    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/plan", json={"request": "Create a workspace for Acme Corp"})

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "create_workspace"
    assert data["planner_mode"] == "rule_based"
