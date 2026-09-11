#!/usr/bin/env python3
"""Call the local MCP server and print a compact result."""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--provider", default="mock", choices=["mock", "aws"])
    parser.add_argument("--service", default="thairath-web")
    parser.add_argument("--resource-id", default="alb/prod-web")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--log-group-name", default="/aws/ecs/your-service")
    parser.add_argument("--time-range-minutes", type=int, default=30)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with streamablehttp_client(args.url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(
                "get_cloud_incident_context",
                {
                    "provider": args.provider,
                    "service": args.service,
                    "resource_id": args.resource_id,
                    "region": args.region,
                    "log_group_name": args.log_group_name,
                    "time_range_minutes": args.time_range_minutes,
                },
            )
            context = json.loads(result.content[0].text)
            summary_result = await session.call_tool("summarize_cloud_incident", {"context": context})
            summary = json.loads(summary_result.content[0].text)

    compact = {
        "available_tools": [tool.name for tool in tools.tools],
        "context": {
            "provider": context.get("provider"),
            "region": context.get("region"),
            "identity": context.get("identity"),
            "alarm_count": len(context.get("alarms", [])) if isinstance(context.get("alarms"), list) else None,
            "alarms_error": context.get("alarms_error"),
            "log_event_count": len(context.get("logs", [])) if isinstance(context.get("logs"), list) else None,
            "logs_error": context.get("logs_error"),
        },
        "triage_summary": summary,
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
