#!/usr/bin/env python3
"""Create temporary AWS monitoring resources and test the MCP tools end to end."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1"))
    parser.add_argument("--keep-resources", action="store_true")
    return parser.parse_args()


def create_fixture(region: str) -> dict[str, str]:
    run_id = uuid.uuid4().hex[:8]
    service = f"ma-mcp-demo-{run_id}"
    resource_id = f"synthetic-resource-{run_id}"
    log_group = f"/ma-mcp-demo/{run_id}"
    log_stream = "app"
    metric_namespace = "MA/MCPDemo"
    metric_name = "IncidentErrorCount"
    alarm_name = f"ma-mcp-demo-alarm-{run_id}"

    logs = boto3.client("logs", region_name=region)
    cloudwatch = boto3.client("cloudwatch", region_name=region)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(logGroupName=log_group, logStreamName=log_stream)
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName=log_stream,
        logEvents=[
            {
                "timestamp": int(time.time() * 1000),
                "message": "ERROR synthetic upstream timeout for MA MCP monitoring demo",
            }
        ],
    )

    cloudwatch.put_metric_data(
        Namespace=metric_namespace,
        MetricData=[
            {
                "MetricName": metric_name,
                "Dimensions": [{"Name": "Service", "Value": service}],
                "Timestamp": datetime.now(timezone.utc),
                "Value": 10,
                "Unit": "Count",
            }
        ],
    )
    cloudwatch.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription="Temporary alarm for MA MCP monitoring demo",
        Namespace=metric_namespace,
        MetricName=metric_name,
        Dimensions=[{"Name": "Service", "Value": service}],
        Statistic="Sum",
        Period=60,
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=1,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
        ActionsEnabled=False,
    )

    # Force alarm state so the test is deterministic without waiting for CloudWatch evaluation.
    cloudwatch.set_alarm_state(
        AlarmName=alarm_name,
        StateValue="ALARM",
        StateReason="Synthetic alarm state for MA MCP monitoring demo",
    )
    wait_for_alarm_state(cloudwatch, alarm_name, "ALARM")

    return {
        "region": region,
        "service": service,
        "resource_id": resource_id,
        "log_group": log_group,
        "log_stream": log_stream,
        "metric_namespace": metric_namespace,
        "metric_name": metric_name,
        "alarm_name": alarm_name,
    }


def wait_for_alarm_state(cloudwatch: Any, alarm_name: str, expected_state: str) -> None:
    deadline = time.time() + 30
    last_state = None
    while time.time() < deadline:
        response = cloudwatch.describe_alarms(AlarmNames=[alarm_name])
        alarms = response.get("MetricAlarms", [])
        if alarms:
            last_state = alarms[0].get("StateValue")
            if last_state == expected_state:
                return
        time.sleep(2)
    raise RuntimeError(f"Alarm {alarm_name} did not reach {expected_state}; last_state={last_state}")


def cleanup_fixture(fixture: dict[str, str]) -> dict[str, Any]:
    region = fixture["region"]
    logs = boto3.client("logs", region_name=region)
    cloudwatch = boto3.client("cloudwatch", region_name=region)
    cleanup: dict[str, Any] = {"deleted": [], "errors": []}

    try:
        cloudwatch.delete_alarms(AlarmNames=[fixture["alarm_name"]])
        cleanup["deleted"].append(fixture["alarm_name"])
    except ClientError as exc:
        cleanup["errors"].append({"resource": fixture["alarm_name"], "error": str(exc)})

    try:
        logs.delete_log_group(logGroupName=fixture["log_group"])
        cleanup["deleted"].append(fixture["log_group"])
    except ClientError as exc:
        cleanup["errors"].append({"resource": fixture["log_group"], "error": str(exc)})

    cleanup["note"] = "CloudWatch custom metrics cannot be deleted manually; they expire automatically after retention."
    return cleanup


async def call_mcp_tool(fixture: dict[str, str]) -> dict[str, Any]:
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            context_result = await session.call_tool(
                "get_cloud_incident_context",
                {
                    "provider": "aws",
                    "service": fixture["service"],
                    "resource_id": fixture["resource_id"],
                    "region": fixture["region"],
                    "log_group_name": fixture["log_group"],
                    "time_range_minutes": 30,
                },
            )
            context = json.loads(context_result.content[0].text)
            summary_result = await session.call_tool("summarize_cloud_incident", {"context": context})
            summary = json.loads(summary_result.content[0].text)

    return {
        "available_tools": [tool.name for tool in tools.tools],
        "context": {
            "provider": context.get("provider"),
            "region": context.get("region"),
            "identity": context.get("identity"),
            "alarm_count": len(context.get("alarms", [])) if isinstance(context.get("alarms"), list) else None,
            "alarm_names": [
                alarm.get("AlarmName")
                for alarm in context.get("alarms", [])
                if isinstance(alarm, dict) and alarm.get("AlarmName", "").startswith("ma-mcp-demo-")
            ],
            "log_event_count": len(context.get("logs", [])) if isinstance(context.get("logs"), list) else None,
            "log_messages": [
                event.get("message")
                for event in context.get("logs", [])
                if isinstance(event, dict)
            ],
            "alarms_error": context.get("alarms_error"),
            "logs_error": context.get("logs_error"),
        },
        "triage_summary": summary,
    }


def wait_for_server() -> None:
    import urllib.request

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/mcp", timeout=1):
                return
        except Exception:
            time.sleep(0.3)


def main() -> None:
    args = parse_args()
    fixture: dict[str, str] | None = None
    server: subprocess.Popen[str] | None = None
    try:
        fixture = create_fixture(args.region)
        env = os.environ.copy()
        env["MOCK_MODE"] = "0"
        env["AWS_DEFAULT_REGION"] = args.region
        server = subprocess.Popen(
            [sys.executable, "server.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_server()
        result = asyncio.run(call_mcp_tool(fixture))
        output = {
            "fixture": fixture,
            "mcp_result": result,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    finally:
        if server is not None:
            server.terminate()
            with suppress(Exception):
                server.wait(timeout=5)
            if server.poll() is None:
                server.kill()
        if fixture is not None and not args.keep_resources:
            cleanup = cleanup_fixture(fixture)
            print(json.dumps({"cleanup": cleanup}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
