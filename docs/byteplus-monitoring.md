# BytePlus Cloud Monitor through the External MCP Server

The same HTTPS MCP service used for AWS can query BytePlus Cloud Monitor. The server may run on AWS EC2: its hosting location does not determine which cloud APIs it can access.

```text
MA Cloud -> HTTPS MCP + Vault Bearer token -> EC2-hosted MCP
  -> AWS CloudWatch through the EC2 instance role
  -> BytePlus Cloud Monitor through separate BytePlus cloud credentials
```

## Tools

- `get_byteplus_metric_data` calls `GetMetricData` for a specific namespace, metric, and resource dimension.
- `get_byteplus_alert_groups` calls `ListAlertGroup` for a resource and time window. It returns one page of alarm history, including any states supplied by the service. History entries are not automatically active incidents.

Both tools return `ok` and a structured result or `query_error`. Check the inner `ok` field as well as the MCP protocol-level error flag. Missing credentials produce an error, never mock data. Empty results do not establish service health.

## Setup

Install `requirements-byteplus.txt`. Configure the following variables only on the MCP server:

```text
BYTEPLUS_ACCESS_KEY=<cloud-access-key>
BYTEPLUS_SECRET_KEY=<cloud-secret-key>
BYTEPLUS_SESSION_TOKEN=<only-for-temporary-credentials>
```

Keep them in a restricted environment file or secret manager. With systemd, use `EnvironmentFile` to inject a root-readable file into the service. The EC2 IAM role cannot authenticate BytePlus requests. MA's MCP Bearer token authenticates the MCP connection; it does not replace cloud credentials.

Deploy `server.py`, `tools.py`, and `byteplus_tools.py` together. Restart the MCP service after installing dependencies and configuring credentials. Reuse the HTTPS endpoint and matching Vault credential described in the [external MCP deployment guide](ma-external-aws-monitoring-mcp.en.md).

## Example Requests

For an ECS CPU User query, substitute a real resource ID:

```json
{
  "namespace": "VCM_ECS",
  "sub_namespace": "Instance",
  "metric_name": "CPUUser",
  "dimensions": {"ResourceID": "i-REPLACE_ME"},
  "region": "ap-southeast-1",
  "time_range_minutes": 30,
  "period": "60s",
  "statistics_method": "avg"
}
```

Pass this object to `get_byteplus_metric_data`. Metric names, dimensions, periods, and statistics must be supported by the relevant cloud product. `CPUUser` represents user-mode CPU usage, not total CPU usage. The documented namespace mapping appears in [Cloud Monitor integration](https://docs.byteplus.com/zh-TW/docs/vmp/Monitoring-cloud-services).

For alarm history, call `get_byteplus_alert_groups`:

```json
{
  "resource_id": "i-REPLACE_ME",
  "region": "ap-southeast-1",
  "time_range_minutes": 60,
  "page_number": 1,
  "page_size": 20
}
```

Time windows are converted to Unix seconds. Inspect `total_count` and request further pages when necessary. See [ListAlertGroup](https://docs.byteplus.com/en/docs/cloudmonitor/ListAlertGroup).

## MA Task

Use a new Agent or Session that discovers the updated MCP tools. Configure its MCP server name to match its `mcp_toolset.McpServerName`, attach the existing endpoint credential through Vault, and instruct it to use the BytePlus tools explicitly:

```text
Query BytePlus Cloud Monitor for the specified ECS resource in ap-southeast-1.
Call get_byteplus_metric_data for VCM_ECS / Instance / CPUUser with ResourceID
set to the supplied instance ID and a 30-minute window. Also call
get_byteplus_alert_groups for that resource over the past 60 minutes.
Report the returned datapoint count, unit, latest value, range, and alert
history. Do not treat an empty alert list or missing datapoints as proof of
health. Distinguish CPU User from total CPU. Do not call AWS tools or change
cloud resources. Explain any query errors.
```

Do not pass these results to the AWS demo's deterministic incident summary as if it understood BytePlus metric semantics. Let MA interpret the returned evidence directly.

## Validation

Local tests:

```bash
.venv/bin/python -m unittest test_byteplus_tools.py
```

The tests validate SDK request construction, resource scoping, pagination arguments, and missing-credential handling. They do not prove remote connectivity.

On 2026-09-11, a real BytePlus ECS resource was queried both directly and through the EC2-hosted HTTPS MCP. The public MCP returned 29 CPU User datapoints (3.24% to 4.39%, latest 3.64% in that window) and an empty resource-scoped alert-history page, with both inner results reporting `ok=true`. These are observations from that query window, not a production health verdict.

MA Cloud validation also completed successfully on 2026-09-11 at 12:43 UTC. Session `sesn-20260911124232-zt82l`, using Agent `agent-20260911124217-qtxhw` and model `seed-2-0-lite-260428`, called both BytePlus tools through the external HTTPS MCP and Vault credential. Both MCP results had `is_error=false` and inner `ok=true`. The session ended normally with `end_turn`.

That MA query returned 29 CPU User datapoints, a range of 3.24% to 4.39%, and a latest value of 3.48% at Unix timestamp `1789130520`. The resource-scoped alert-history page was empty. MA correctly distinguished user-mode CPU from total CPU and did not equate an empty alert history with overall health.

This example does not create BytePlus resources or inject faults. TLS log search, alert creation, remediation, and continuous scheduling are outside the current implementation.

SDK source: [official BytePlus Python SDK](https://github.com/byteplus-sdk/byteplus-python-sdk-v2).
