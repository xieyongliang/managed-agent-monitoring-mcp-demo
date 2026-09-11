#!/usr/bin/env python3
"""Small monitoring tools that can be exposed through MCP or Custom Tool."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimeRange:
    start_epoch_ms: int
    end_epoch_ms: int
    start_epoch_s: int
    end_epoch_s: int


def build_time_range(minutes: int) -> TimeRange:
    now_s = int(time.time())
    start_s = now_s - minutes * 60
    return TimeRange(
        start_epoch_ms=start_s * 1000,
        end_epoch_ms=now_s * 1000,
        start_epoch_s=start_s,
        end_epoch_s=now_s,
    )


def run_json_command(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "command": args,
            "error": completed.stderr.strip() or completed.stdout.strip(),
        }
    try:
        return {"ok": True, "command": args, "data": json.loads(completed.stdout)}
    except json.JSONDecodeError:
        return {"ok": True, "command": args, "data": completed.stdout}


def mock_incident_context(
    provider: str,
    service: str,
    resource_id: str,
    time_range_minutes: int,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "service": service,
        "resource_id": resource_id,
        "time_range_minutes": time_range_minutes,
        "alarms": [
            {
                "name": "high-5xx-rate",
                "state": "ALARM",
                "severity": "high",
                "reason": "5xx rate stayed above 5% for 3 datapoints.",
            }
        ],
        "metrics": [
            {"name": "CPUUtilization", "stat": "Average", "latest": 42.3, "unit": "Percent"},
            {"name": "HTTPCode_ELB_5XX_Count", "stat": "Sum", "latest": 183, "unit": "Count"},
            {"name": "TargetResponseTime", "stat": "p95", "latest": 2.7, "unit": "Seconds"},
        ],
        "logs": [
            {
                "timestamp": "recent",
                "message": "ERROR upstream timeout when calling payment-profile service",
            },
            {
                "timestamp": "recent",
                "message": "WARN retry exhausted for dependency payment-profile",
            },
        ],
    }


def get_aws_incident_context(
    region: str,
    service: str,
    resource_id: str,
    log_group_name: str,
    time_range_minutes: int,
) -> dict[str, Any]:
    time_range = build_time_range(time_range_minutes)

    alarms = run_json_command(
        [
            "aws",
            "cloudwatch",
            "describe-alarms",
            "--state-value",
            "ALARM",
            "--region",
            region,
            "--output",
            "json",
        ]
    )

    logs = run_json_command(
        [
            "aws",
            "logs",
            "filter-log-events",
            "--region",
            region,
            "--log-group-name",
            log_group_name,
            "--filter-pattern",
            "ERROR ?Timeout ?Exception",
            "--start-time",
            str(time_range.start_epoch_ms),
            "--end-time",
            str(time_range.end_epoch_ms),
            "--limit",
            "20",
            "--output",
            "json",
        ]
    )

    return {
        "provider": "aws",
        "region": region,
        "service": service,
        "resource_id": resource_id,
        "time_range_minutes": time_range_minutes,
        "alarms": alarms,
        "logs": logs,
        "metrics_note": "Add service-specific get-metric-data queries after choosing the resource type.",
    }


def get_aws_incident_context_boto3(
    region: str,
    service: str,
    resource_id: str,
    log_group_name: str,
    time_range_minutes: int,
) -> dict[str, Any]:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    time_range = build_time_range(time_range_minutes)
    cloudwatch = boto3.client("cloudwatch", region_name=region)
    logs = boto3.client("logs", region_name=region)
    sts = boto3.client("sts", region_name=region)

    result: dict[str, Any] = {
        "provider": "aws",
        "region": region,
        "service": service,
        "resource_id": resource_id,
        "time_range_minutes": time_range_minutes,
    }

    try:
        identity = sts.get_caller_identity()
        result["identity"] = {
            "account": identity.get("Account"),
            "arn": identity.get("Arn"),
        }
    except (BotoCoreError, ClientError) as exc:
        result["identity_error"] = str(exc)

    try:
        result["alarms"] = cloudwatch.describe_alarms(StateValue="ALARM").get("MetricAlarms", [])
    except (BotoCoreError, ClientError) as exc:
        result["alarms_error"] = str(exc)

    try:
        result["logs"] = logs.filter_log_events(
            logGroupName=log_group_name,
            filterPattern="ERROR ?Timeout ?Exception",
            startTime=time_range.start_epoch_ms,
            endTime=time_range.end_epoch_ms,
            limit=20,
        ).get("events", [])
    except (BotoCoreError, ClientError) as exc:
        result["logs_error"] = str(exc)

    result["metrics_note"] = "Add service-specific get_metric_data queries after choosing the resource type."
    return result


def get_incident_context(
    provider: str = "mock",
    service: str = "web",
    resource_id: str = "demo-resource",
    region: str = "ap-southeast-1",
    log_group_name: str = "/aws/ecs/demo",
    time_range_minutes: int = 30,
) -> dict[str, Any]:
    """Return alarms, metrics, and logs for incident triage."""

    mock_mode = os.getenv("MOCK_MODE", "1") != "0"
    if mock_mode or provider == "mock":
        return mock_incident_context(provider, service, resource_id, time_range_minutes)

    if provider == "aws":
        try:
            import boto3  # noqa: F401

            return get_aws_incident_context_boto3(
                region=region,
                service=service,
                resource_id=resource_id,
                log_group_name=log_group_name,
                time_range_minutes=time_range_minutes,
            )
        except ModuleNotFoundError:
            pass
        return get_aws_incident_context(
            region=region,
            service=service,
            resource_id=resource_id,
            log_group_name=log_group_name,
            time_range_minutes=time_range_minutes,
        )

    return {
        "ok": False,
        "error": f"provider {provider!r} is not implemented yet",
        "supported_providers": ["mock", "aws"],
    }


def summarize_incident(context: dict[str, Any]) -> dict[str, Any]:
    """A deterministic triage summary used to test the tool loop without an LLM."""

    alarms = context.get("alarms") if isinstance(context.get("alarms"), list) else []
    logs = context.get("logs") if isinstance(context.get("logs"), list) else []
    evidence_text = json.dumps({"alarms": alarms, "logs": logs}, ensure_ascii=False).lower()
    has_incident_signal = bool(alarms) or "error" in evidence_text or "timeout" in evidence_text
    has_tool_error = any(key.endswith("_error") for key in context)
    if has_incident_signal:
        severity = "high"
        suspected_cause = "dependency timeout or elevated 5xx errors"
    elif has_tool_error:
        severity = "unknown"
        suspected_cause = "monitoring query was incomplete; validate tool errors first"
    else:
        severity = "low"
        suspected_cause = "no strong incident signal"
    return {
        "severity": severity,
        "suspected_cause": suspected_cause,
        "impact": "possible user-facing errors" if severity == "high" else "no confirmed user impact",
        "next_steps": [
            "Check active alarms and recent error logs.",
            "Verify upstream dependency latency and error rate.",
            "Notify on-call owner with the structured incident summary.",
        ],
        "source_provider": context.get("provider"),
        "resource_id": context.get("resource_id"),
    }
