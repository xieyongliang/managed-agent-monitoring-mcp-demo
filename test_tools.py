#!/usr/bin/env python3
"""Run the monitoring tool logic without starting an MCP server."""

from __future__ import annotations

import json

from tools import get_incident_context, summarize_incident


def main() -> None:
    context = get_incident_context(
        provider="mock",
        service="thairath-web",
        resource_id="alb/prod-web",
        time_range_minutes=30,
    )
    summary = summarize_incident(context)
    print(
        json.dumps(
            {
                "incident_context": context,
                "triage_summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
