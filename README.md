# Monitoring MCP Demo

This is a minimal runnable example for a Managed Agent monitoring POC.

For the full walkthrough and verified AWS E2E result, see [`docs/managed-agent-monitoring-poc.md`](docs/managed-agent-monitoring-poc.md).

For external AWS MCP deployment, HTTPS authentication, and MA Cloud integration, see [Accessing an External AWS Monitoring MCP Server from MA (English)](docs/ma-external-aws-monitoring-mcp.en.md) or the [Chinese version](docs/ma-external-aws-monitoring-mcp.md).

The demo has two layers:

- `tools.py`: provider-specific monitoring functions. It can run without MCP.
- `server.py`: exposes the same functions as MCP tools through `streamable-http`.

## Run the local tool test

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python test_tools.py
```

Expected behavior:

- returns mock alarms, metrics, and logs
- produces a deterministic incident triage summary

## Start the MCP server

Install the MCP package first:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Then start the server:

```bash
.venv/bin/python server.py
```

In another terminal, call the MCP tools:

```bash
.venv/bin/python client_test.py --provider mock
```

For Managed Agent integration, deploy this server as a public HTTPS service that MA can reach. Localhost is useful for development, but MA cloud sessions cannot access a developer laptop localhost directly.

## Replace mock data with AWS

The tool supports AWS through `boto3`, with an AWS CLI fallback.

Then run:

```bash
AWS_ACCESS_KEY_ID="..." \
AWS_SECRET_ACCESS_KEY="..." \
AWS_DEFAULT_REGION="ap-southeast-1" \
MOCK_MODE=0 .venv/bin/python server.py
```

In another terminal:

```bash
.venv/bin/python client_test.py \
  --provider aws \
  --region ap-southeast-1 \
  --log-group-name "/aws/ecs/your-service"
```

The first AWS version uses:

- STS `GetCallerIdentity`
- CloudWatch `DescribeAlarms`
- CloudWatch Logs `FilterLogEvents`

After the target resource type is clear, add service-specific `aws cloudwatch get-metric-data` queries.

## Full AWS E2E test

This creates temporary AWS resources, calls the MCP tools, then cleans up:

- CloudWatch Logs log group and stream
- one synthetic ERROR log event
- one custom CloudWatch metric datapoint
- one CloudWatch alarm forced into `ALARM` state for deterministic testing

```bash
AWS_ACCESS_KEY_ID="..." \
AWS_SECRET_ACCESS_KEY="..." \
AWS_DEFAULT_REGION="ap-southeast-1" \
.venv/bin/python aws_e2e_test.py
```

The alarm and log group are deleted at the end. CloudWatch custom metrics cannot be manually deleted; they expire automatically after retention.

## Next BytePlus implementation

Add BytePlus Cloud Monitor and TLS inside `tools.py`:

- Cloud Monitor: `GetMetricData`
- TLS: `SearchLogs`

Keep credentials in the tool server environment or Vault. Do not pass cloud access keys through the agent prompt.
