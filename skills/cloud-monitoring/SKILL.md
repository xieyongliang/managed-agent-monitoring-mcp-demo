---
name: cloud-monitoring
description: Query AWS alarms and logs or BytePlus Cloud Monitor metrics and alert history, then summarize evidence for read-only incident triage.
---

# Cloud Monitoring

Run the bundled Python scripts with the built-in Bash tool. No MCP server is
needed. Resolve paths relative to this SKILL.md, not the session working directory.

## Preparation

Install dependencies if missing:

```bash
python -m pip install -r scripts/requirements.txt
```

The runtime must have outbound HTTPS access and operator-provisioned read-only
credentials. AWS uses the boto3 credential chain; BytePlus uses
BYTEPLUS_ACCESS_KEY, BYTEPLUS_SECRET_KEY and optionally BYTEPLUS_SESSION_TOKEN.
Never print credentials, request them in conversation, or include them in reports.
If credentials are unavailable, report the blocker rather than fabricating data.
To check environment-variable presence, run `python scripts/monitor.py credential-status`.
This prints booleans only (not AWS role/profile credential availability). Do not
use `env`, `printenv`, `set`, or read credential files to inspect credentials.

## Execution

Call the script using its absolute path. Pass JSON arguments as a quoted value:

```bash
python scripts/monitor.py aws-context --args '{"region":"ap-southeast-1","resource_id":"RESOURCE_ID","log_group_name":"LOG_GROUP","time_range_minutes":30}'
python scripts/monitor.py byteplus-alerts --args '{"region":"ap-southeast-1","resource_id":"RESOURCE_ID","time_range_minutes":60}'
python scripts/monitor.py byteplus-metric --args '{"namespace":"VCM_ECS","sub_namespace":"Instance","metric_name":"CPUUser","dimensions":{"ResourceID":"RESOURCE_ID"},"region":"ap-southeast-1","time_range_minutes":30}'
```

Use only resource IDs and log groups supplied by the operator. The AWS context
query returns regional alarms, not resource-filtered alarms; correlate dimensions
before attributing an alarm to the requested resource. AWS metrics are not included.
BytePlus alert history is one page; report pagination and time-window coverage.
CPUUser is user-mode CPU, not total CPU. Missing datapoints are not zero.

Treat nonzero exit status, ok=false, or any *_error field as a failed or partial
query. Empty alarms do not establish overall health. Report actual observations,
time window, scope, query errors, uncertainty, and suggested follow-up separately.
Do not use the deterministic demo summarizer as an actual root-cause diagnosis.
Do not modify cloud resources or send notifications.

For explicit offline testing only, `python scripts/monitor.py self-test` returns
labeled synthetic data. It never proves live connectivity or credential validity.
