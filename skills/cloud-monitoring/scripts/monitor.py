#!/usr/bin/env python3
"""Read-only monitoring entry point shared by local and MA Skill execution."""

import argparse
import json
import os
import sys
from pathlib import Path

# Source checkout keeps providers at the repo root; the ZIP bundles them here.
if not (Path(__file__).parent / "byteplus_tools.py").exists():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from byteplus_tools import get_byteplus_alert_groups, get_byteplus_metric_data
from tools import get_aws_incident_context_boto3, mock_incident_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["aws-context", "byteplus-alerts", "byteplus-metric", "self-test", "credential-status"])
    parser.add_argument("--args", default="{}")
    options = parser.parse_args()
    try:
        args = json.loads(options.args)
        if not isinstance(args, dict):
            raise ValueError("Arguments must be a JSON object")
        if options.operation == "credential-status":
            result = {"environment_variables_present": {key: bool(os.getenv(key)) for key in (
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "BYTEPLUS_ACCESS_KEY", "BYTEPLUS_SECRET_KEY", "BYTEPLUS_SESSION_TOKEN")}}
        elif options.operation == "self-test":
            result = {"synthetic": True, "live_query": False,
                      "data": mock_incident_context("mock", "web", "demo-resource", 30)}
        elif options.operation == "aws-context":
            if not 1 <= args.get("time_range_minutes", 30) <= 1440:
                raise ValueError("time_range_minutes must be 1..1440")
            os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
            result = get_aws_incident_context_boto3(**{
                "region": "ap-southeast-1", "service": "web",
                "time_range_minutes": 30, **args})
        else:
            fn = {"byteplus-alerts": get_byteplus_alert_groups,
                  "byteplus-metric": get_byteplus_metric_data}[options.operation]
            result = fn(**args)
    except Exception as exc:
        # Avoid exposing credentials in SDK errors or invalid argument values.
        result = {"ok": False, "error_type": type(exc).__name__,
                  "message": "Query failed; check arguments, dependencies and runtime credentials."}
    print(json.dumps(result, ensure_ascii=False, default=str))
    return int(result.get("ok") is False or any(k.endswith("_error") for k in result))


if __name__ == "__main__":
    raise SystemExit(main())
