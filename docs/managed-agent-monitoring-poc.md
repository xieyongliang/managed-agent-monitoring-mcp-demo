# Managed Agent Monitoring MCP POC

This document describes a minimal proof of concept for using ModelArk Managed Agent with MCP tools to support cloud incident triage across AWS and, later, BytePlus Cloud.

## Goal

The goal is not to replace existing monitoring platforms. The goal is to let a Managed Agent call approved monitoring tools, collect evidence, and turn scattered alerts, metrics, and logs into an actionable incident summary.

For a customer such as Thairath, this is a good first POC shape:

1. Detect or receive an incident signal.
2. Query cloud alarms, recent metrics, and error logs.
3. Let the agent summarize severity, suspected cause, impact, and next steps.
4. Notify an operator or create a ticket.
5. Keep remediation read-only at first, then add human-approved actions later.

## Architecture

```text
Managed Agent
  -> MCP Tool: get_cloud_incident_context
  -> MCP Server / Tool Executor
      -> AWS STS
      -> AWS CloudWatch
      -> AWS CloudWatch Logs
      -> BytePlus Cloud Monitor / TLS in the next phase
  -> MCP Tool: summarize_cloud_incident
  -> Structured incident summary
```

Managed Agent should not directly hold cloud access keys in the prompt. Cloud credentials should live in the MCP server environment, Vault, or another controlled credential layer.

## Implemented Tools

This POC exposes two MCP tools:

```text
get_cloud_incident_context
summarize_cloud_incident
```

`get_cloud_incident_context` can run in two modes:

- `mock`: returns deterministic sample alarms, metrics, and logs.
- `aws`: uses `boto3` to call real AWS APIs.

The AWS path currently calls:

- STS `GetCallerIdentity`
- CloudWatch `DescribeAlarms`
- CloudWatch Logs `FilterLogEvents`

`summarize_cloud_incident` is intentionally deterministic in this POC. In a real MA session, the Managed Agent's main model can perform the final reasoning using the structured evidence returned by the tool.

## Local Setup

```bash
cd /path/to/monitoring-mcp-demo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Mock Test

Run the tool logic directly:

```bash
.venv/bin/python test_tools.py
```

Start the MCP server:

```bash
.venv/bin/python server.py
```

In another terminal, call the MCP tools:

```bash
.venv/bin/python client_test.py --provider mock
```

Expected result:

- MCP server starts on `http://127.0.0.1:8000`.
- The client lists `get_cloud_incident_context` and `summarize_cloud_incident`.
- The mock incident summary returns `severity=high`.

## AWS E2E Test

The E2E script creates temporary AWS resources, queries them through the MCP tool, then cleans up.

It creates:

- one CloudWatch Logs log group
- one log stream
- one synthetic `ERROR` log event
- one custom CloudWatch metric datapoint
- one CloudWatch alarm forced into `ALARM` state for deterministic testing

Run:

```bash
AWS_ACCESS_KEY_ID="..." \
AWS_SECRET_ACCESS_KEY="..." \
AWS_DEFAULT_REGION="ap-southeast-1" \
.venv/bin/python aws_e2e_test.py
```

Expected result:

```json
{
  "alarm_count": 1,
  "log_event_count": 1,
  "triage_summary": {
    "severity": "high",
    "suspected_cause": "dependency timeout or elevated 5xx errors",
    "impact": "possible user-facing errors"
  }
}
```

Cleanup behavior:

- the temporary CloudWatch alarm is deleted
- the temporary log group is deleted
- custom CloudWatch metrics are not manually deletable and expire automatically

## Verified Result

The AWS E2E test was run successfully in `ap-southeast-1`.

Observed result:

```json
{
  "alarm_count": 1,
  "alarm_names": ["ma-mcp-demo-alarm-1d78c69d"],
  "log_event_count": 1,
  "log_messages": ["ERROR synthetic upstream timeout for MA MCP monitoring demo"],
  "triage_summary": {
    "severity": "high",
    "suspected_cause": "dependency timeout or elevated 5xx errors",
    "impact": "possible user-facing errors"
  }
}
```

Cleanup also succeeded:

```json
{
  "deleted": [
    "ma-mcp-demo-alarm-1d78c69d",
    "/ma-mcp-demo/1d78c69d"
  ],
  "errors": []
}
```

## Managed Agent Integration

For local development, the MCP server runs on:

```text
http://127.0.0.1:8000/mcp
```

For Managed Agent cloud integration, this server must be deployed to a network endpoint reachable by MA, preferably a public HTTPS endpoint with authentication.

Example MA-level tool flow:

```text
User or alert webhook:
  "Investigate recent errors for service X."

Managed Agent:
  1. Calls get_cloud_incident_context.
  2. Reads structured alarms and logs.
  3. Produces severity, suspected root cause, impact, and next steps.
  4. Optionally calls a notification or ticket creation tool.
```

## BytePlus Extension

The same pattern can be extended to BytePlus:

- Cloud Monitor `GetMetricData` for metrics.
- TLS `SearchLogs` for logs.
- Event or alarm APIs for active alerts if available in the customer's setup.

Recommended next tools:

```text
list_active_alarms(provider, region)
get_resource_metrics(provider, service, resource_id, metric_names, time_range)
search_error_logs(provider, log_group_or_topic, query, time_range)
send_incident_notification(channel, summary)
```

## Security Notes

- Do not commit cloud access keys.
- Do not put AK/SK in Managed Agent prompts.
- Prefer temporary credentials, IAM roles, or Vault-managed credentials.
- Keep the first POC read-only.
- Add human approval before any remediation tool such as restart, rollback, scaling, or firewall changes.
