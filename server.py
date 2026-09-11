#!/usr/bin/env python3
"""MCP server exposing minimal cloud monitoring tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools import get_incident_context, summarize_incident
from byteplus_tools import get_byteplus_alert_groups, get_byteplus_metric_data


mcp = FastMCP("cloud-monitoring-demo")
mcp.tool()(get_byteplus_alert_groups)
mcp.tool()(get_byteplus_metric_data)


@mcp.tool()
def get_cloud_incident_context(
    provider: str = "mock",
    service: str = "web",
    resource_id: str = "demo-resource",
    region: str = "ap-southeast-1",
    log_group_name: str = "/aws/ecs/demo",
    time_range_minutes: int = 30,
) -> dict:
    """Fetch alarms, metrics, and logs for incident triage."""
    return get_incident_context(
        provider=provider,
        service=service,
        resource_id=resource_id,
        region=region,
        log_group_name=log_group_name,
        time_range_minutes=time_range_minutes,
    )


@mcp.tool()
def summarize_cloud_incident(context: dict) -> dict:
    """Create a compact incident triage summary from tool evidence."""
    return summarize_incident(context)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
