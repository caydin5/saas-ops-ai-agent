"""
Mock tools for the SaaS Ops AI Agent.

In a real production system, these functions would call:
- REST APIs
- databases
- internal services
- workflow automation systems
- browser automation tasks

For this MVP, they return fake but realistic responses.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_workspace(customer_name: str) -> dict[str, Any]:
    """
    Mock tool that simulates creating a customer workspace.

    Args:
        customer_name: Name of the customer who needs a workspace.

    Returns:
        A dictionary representing the created workspace.
    """

    logger.info("Creating workspace for customer: %s", customer_name)

    return {
        "workspace_id": f"ws_{customer_name.lower().replace(' ', '_')}",
        "customer_name": customer_name,
        "created": True,
    }


def generate_usage_report(customer_name: str, period: str = "last month") -> dict[str, Any]:
    """
    Mock tool that simulates generating a usage report.

    Args:
        customer_name: Name of the customer.
        period: Reporting period, such as "last month".

    Returns:
        A fake usage report with realistic fields.
    """

    logger.info("Generating usage report for customer=%s period=%s", customer_name, period)

    return {
        "customer_name": customer_name,
        "period": period,
        "active_users": 128,
        "api_calls": 8421,
        "report_ready": True,
    }


def search_documentation(query: str) -> dict[str, Any]:
    """
    Mock tool that simulates searching product documentation.

    Args:
        query: The user's documentation search query.

    Returns:
        A fake list of matching documentation results.
    """

    logger.info("Searching documentation for query: %s", query)

    return {
        "query": query,
        "matches": [
            {
                "title": "Workspace Management API",
                "summary": "Explains how to create, update, and archive customer workspaces.",
            },
            {
                "title": "Usage Reports API",
                "summary": "Explains how to generate usage reports by customer and time period.",
            },
        ],
    }