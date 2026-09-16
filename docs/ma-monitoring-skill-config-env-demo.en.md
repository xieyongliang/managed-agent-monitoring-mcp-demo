# MA Cloud + Skill + config.env: AWS and BytePlus Monitoring Demo

Validated on September 16, 2026. Audience: customer engineering, solutions teams, and demo presenters.

[中文版本](ma-monitoring-skill-config-env-demo.zh-CN.md)

## 1. Objective and Verified Outcome

This example runs a custom monitoring Skill inside ModelArk Managed Agents (MA). The Agent uses built-in Bash to execute Python SDK calls, retrieves AWS and BytePlus monitoring data, and summarizes the returned evidence.

**Real cloud queries succeeded inside MA Cloud. No MCP server or customer-side executor was required.**

| Capability | Verified result |
| --- | --- |
| Load a custom Skill and execute Python in MA | Succeeded |
| Supply SDK signing credentials through Environment config.env | Succeeded |
| Query BytePlus ECS CPUUser | Succeeded; 29 real datapoints returned |
| Query BytePlus alert history | Succeeded; empty result in this test |
| Query AWS identity, CloudWatch alarms, and logs | Succeeded; empty alarm and matching-log results in this test |
| Summarize tool results with the MA model | Succeeded; Session finished with end_turn |
| Delete temporary Session and Environment | Succeeded; subsequent reads could not retrieve them |

This is an **on-demand, read-only query demo**. It does not implement continuous scheduling, notifications, or automatic remediation, and does not establish long-term production reliability. Reproduction should demonstrate the same workflow, not identical metric values at different times.

## 2. Architecture and Responsibilities

```text
Operator / ArkCLI
  | Upload Skill; configure Agent; create Environment and Session
  v
MA Cloud Session
  +-- Main model: interpret tasks, invoke tools, summarize evidence
  +-- Custom Skill: operating instructions and Python monitoring scripts
  +-- Built-in Bash: execute scripts inside MA Cloud
  +-- Environment config.env: runtime credentials for this test
       |
       +-- boto3 --> AWS STS / CloudWatch / CloudWatch Logs
       +-- BytePlus SDK --> Cloud Monitor
  |
  v
Structured query results --> MA summary with scope and limitations
```

- **Skill:** packages code and instructions; it is neither a standalone service nor a scheduler.
- **MA:** hosts the model and cloud execution environment.
- **SDK:** reads runtime credentials, computes request signatures locally, and calls cloud APIs over HTTPS.
- **ArkCLI:** manages MA resources; local sign-in does not automatically supply cloud SDK credentials inside a Session.
- **config.env:** an environment-variable map in Environment configuration, **not a disk file named config.env**.

Requests in this test originated from MA Cloud, not the EC2 host used in the earlier MCP demo. MCP remains an alternative for centralized authorization and shared tool services, but is not a prerequisite here.

## 3. Source Files

Repository: [managed-agent-monitoring-mcp-demo](https://github.com/xieyongliang/managed-agent-monitoring-mcp-demo). Its name reflects the original MCP implementation; this guide covers its Skill-based path.

> Version note: this guide is maintained alongside the Skill implementation. Before presenting, check out a version containing these files, record the demo commit, and verify packaging from a clean checkout.

| File | Purpose |
| --- | --- |
| build_monitoring_skill.py | Build the Skill ZIP using an explicit allowlist |
| skills/cloud-monitoring/SKILL.md | Monitoring instructions read by MA |
| skills/cloud-monitoring/scripts/monitor.py | Unified command entry point |
| skills/cloud-monitoring/scripts/requirements.txt | SDK dependencies |
| tools.py | AWS queries; bundled into the Skill |
| byteplus_tools.py | BytePlus queries; bundled into the Skill |
| test_monitoring_skill.py and test_byteplus_tools.py | Local regression tests |

The archive contains exactly five files, with no credentials, configuration files, virtual environment, or MCP server:

```text
cloud-monitoring/
  SKILL.md
  scripts/
    monitor.py
    requirements.txt
    tools.py
    byteplus_tools.py
```

## 4. Prerequisites

### 4.1 Accounts and Connectivity

1. Enable MA for the BytePlus account and install and authenticate ArkCLI.
2. Use the intended BytePlus profile. This test used ap-southeast-1; do not mix credentials or API addresses from another product.
3. Select an MA model available to the account. The tested model was seed-2-0-lite-260428.
4. Allow outbound access to the required dependency repositories and AWS/BytePlus APIs. This test used unrestricted networking; review tighter egress policies separately for production.
5. Prepare an approved AWS log group, region, and resource ID, and a BytePlus ECS resource with monitoring data.

Run the following from the repository root to verify authentication and configuration:

```bash
arkcli auth status --format json
arkcli profile show --format json
arkcli agent model list --format json
```

Resolve expired authentication or missing service activation first. Switching credential types is not a workaround for those requirements.

### 4.2 Three Different Credential Types

| Credential | Purpose | Replaces cloud monitoring AK/SK? |
| --- | --- | --- |
| BytePlus SSO | Manage MA resources using ArkCLI | No |
| ModelArk API key | Supported ModelArk data-plane API calls | No |
| AWS / BytePlus cloud AK/SK, plus session token if applicable | Sign requests to the respective cloud APIs | Yes; these are the credentials needed by the SDKs |

Use least-privilege, preferably short-lived credentials. The AWS path calls GetCallerIdentity, DescribeAlarms, and FilterLogEvents. The BytePlus path calls GetMetricData and ListAlertGroup. Have the customer's administrator configure IAM permissions for the actual services, resources, and organization policies; this guide does not supply an unverified generic policy.

**Security boundary:** ordinary config.env is readable configuration, not a vault. An Agent capable of executing scripts can also access these variables. Never place credentials in Skill source, system prompts, chat, setup-script source, Git, or screenshots. Do not use root credentials for a customer demo. The test identified the AWS principal as root; this must be replaced for future demonstrations.

## 5. Reproduction Walkthrough

### Step 1: Validate and Package the Skill

```bash
python3 -m unittest test_monitoring_skill.py test_byteplus_tools.py
python3 build_monitoring_skill.py --output /tmp/cloud-monitoring-skill.zip
arkcli agent skill create --zip /tmp/cloud-monitoring-skill.zip --format json
```

Record the returned Skill ID and version. All five local regression tests passed in this validation. These tests do not call live cloud APIs and do not replace the cloud validation below.

### Step 2: Configure the Agent

Create or select a dedicated demo Agent in the MA console:

- Select a model available to the account; this test used seed-2-0-lite-260428.
- Attach the uploaded custom Skill and pin its validated version.
- Ensure built-in Bash/read are available; do not configure an MCP server.
- Apply the following system instruction and record the Agent ID and version:

```text
Use the cloud-monitoring skill and built-in bash/read tools for read-only
monitoring. Never use MCP or expose credentials. Distinguish synthetic tests,
partial queries and live evidence. Do not modify infrastructure.
```

System instructions guide behavior; they are not an authorization boundary. Cloud IAM permissions must enforce read-only access.

During testing, the CLI's high-level Agent creation path encountered a ListAgents InputSchema decoding compatibility error. The successful run reused an existing Agent. Prepare and validate the Agent before a customer demo. If this error occurs, use the console to create the Agent and report the CLI issue rather than switching cloud accounts.

### Step 3: Create a Dedicated Environment with config.env

The following illustrates the configuration shape. **The placeholders are not real credentials and cannot be used for live queries.**

```json
{
  "Name": "arkcli-monitoring-skill-demo",
  "Config": {
    "Type": "cloud",
    "Networking": {"Type": "unrestricted"},
    "Env": {
      "AWS_ACCESS_KEY_ID": "<AWS_ACCESS_KEY_ID>",
      "AWS_SECRET_ACCESS_KEY": "<AWS_SECRET_ACCESS_KEY>",
      "BYTEPLUS_ACCESS_KEY": "<BYTEPLUS_ACCESS_KEY>",
      "BYTEPLUS_SECRET_KEY": "<BYTEPLUS_SECRET_KEY>"
    }
  }
}
```

Temporary credentials also require AWS_SESSION_TOKEN or BYTEPLUS_SESSION_TOKEN as applicable. Do not store the real payload in the repository or shell history. Do not display full create/get responses: they can contain the original values.

This minimal creation example follows the same input/capture approach used by the test driver: hidden interactive input, a JSON request passed through stdin, and output restricted to the resource ID. Run it in a normal interactive terminal with tracing, debug logging, and screen recording disabled. If creation times out, inspect the console for the unique name before retrying.

```bash
python3 - <<'PY'
import getpass
import json
import os
import subprocess
import time

keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
        "BYTEPLUS_ACCESS_KEY", "BYTEPLUS_SECRET_KEY"]
credentials = {key: getpass.getpass(key + ": ") for key in keys}
if not all(credentials.values()):
    raise SystemExit("Required credential missing; no Environment created")
for key in ["AWS_SESSION_TOKEN", "BYTEPLUS_SESSION_TOKEN"]:
    value = getpass.getpass(key + " (optional): ")
    if value:
        credentials[key] = value
name = "arkcli-monitoring-demo-" + str(int(time.time()))
print("Environment name:", name)
payload = {"Name": name, "Config": {
    "Type": "cloud", "Networking": {"Type": "unrestricted"},
    "Env": credentials}}
cli_env = dict(os.environ, ARKCLI_NO_UPDATE_NOTIFIER="1",
    ARKCLI_CALLER_TYPE="ai_agent", ARKCLI_CALLER_NAME="demo-driver",
    ARKCLI_SKILL_NAME="arkcli-agent")
try:
    proc = subprocess.run(
        ["arkcli", "agent", "env", "create", "--file", "-", "--format", "json"],
        input=json.dumps(payload), capture_output=True, text=True,
        env=cli_env, timeout=90)
except subprocess.TimeoutExpired:
    raise SystemExit("Outcome unknown; inspect by name before retrying")
if proc.returncode:
    raise SystemExit("Create failed; response withheld to protect credentials")
data = json.loads(proc.stdout)
result = data.get("Result", data)
environment_id = result.get("Id", result.get("id"))
if not environment_id:
    raise SystemExit("No ID parsed; inspect by name; do not print raw response")
print("Environment ID:", environment_id)
PY
```

The actual test used a private driver with the same configuration and stdin/capture mechanism. This interactive adaptation is not an additional cloud test and does not implement production credential management or automatic cleanup.

### Step 4: Create a Session

Replace the placeholders with the actual IDs. Restrict output to the Session ID to avoid displaying resolved environment configuration:

```bash
arkcli agent session create \
  --agent-id <AGENT_ID> \
  --agent-version <AGENT_VERSION> \
  --environment-id <ENVIRONMENT_ID> \
  --title "arkcli-monitoring-skill-demo" \
  --format json --transform Result.Id
```

If the installed CLI uses a different response structure, do not remove filtering and display the raw response. Use a capture driver to parse Result.Id or the top-level id. The actual test captured the complete response privately and printed only the ID.

### Step 5: Ask MA to Run Live Queries

Send the following task after substituting approved customer test resources. Resource IDs and log group names are task parameters; credentials are not.

```text
Use the cloud-monitoring Skill to run one real read-only monitoring check.
Do not use MCP. Read SKILL.md first, then install scripts/requirements.txt.
Credentials are already supplied through Environment config.env.
Never print secrets or run env/printenv. Use credential-status only to report
environment-variable presence booleans.

Region: ap-southeast-1.
BytePlus: ECS <BP_ECS_ID>, CPUUser for the last 30 minutes and alert history
for the last 60 minutes.
AWS: resource <AWS_RESOURCE_ID>, log group <AWS_LOG_GROUP>, matching logs for
the last 60 minutes, and regional monitoring alarms in ALARM state.

Execute Skill commands through Python subprocess with a 70-second timeout
per command. Capture stdout/stderr and replace any exact credential values
with [REDACTED] before output. Limit dependency installation to 90 seconds.
Do not print unfiltered SDK errors.

Summarize actual tool evidence only. Do not substitute self-test for live queries.
Report scope, time window, result counts, errors, and gaps in coverage.
CPUUser is not total CPU. Empty alarms/logs do not establish resource health.
Correlate AWS alarm dimensions before attributing an alarm to a resource.
This script does not query AWS CPU metrics.
Stop after the check. Do not modify infrastructure or send notifications.
```

Alternatively, send the non-secret task using ArkCLI and wait for the result:

```bash
arkcli agent session events send <SESSION_ID> \
  --text "<The task above with approved resource parameters>" \
  --poll --wait-timeout 300 --format jsonl
```

Prompt-based redaction is not a security boundary. To reduce variation, the actual test provided an explicit Python wrapper that captured four subprocess outputs, replaced exact non-empty values from the six credential environment variables, emitted structured results, and enforced a 70-second timeout per command. Use low-privilege credentials, restrict log access, and review events before screen sharing.

The wrapper invokes these commands **inside MA, not on the presenter's laptop**:

```bash
timeout 90 python -m pip install -r /mnt/skills/cloud-monitoring/scripts/requirements.txt

python /mnt/skills/cloud-monitoring/scripts/monitor.py credential-status

python /mnt/skills/cloud-monitoring/scripts/monitor.py byteplus-metric \
  --args '{"namespace":"VCM_ECS","sub_namespace":"Instance","metric_name":"CPUUser","dimensions":{"ResourceID":"<BP_ECS_ID>"},"region":"ap-southeast-1","time_range_minutes":30}'

python /mnt/skills/cloud-monitoring/scripts/monitor.py byteplus-alerts \
  --args '{"region":"ap-southeast-1","resource_id":"<BP_ECS_ID>","time_range_minutes":60}'

python /mnt/skills/cloud-monitoring/scripts/monitor.py aws-context \
  --args '{"region":"ap-southeast-1","resource_id":"<AWS_RESOURCE_ID>","log_group_name":"<AWS_LOG_GROUP>","time_range_minutes":60}'
```

### Step 6: Verify Tool Evidence

Do not rely only on the Agent's final message. Inspect the actual tool events:

- Every operation has exit_code 0; BytePlus returns ok: true.
- AWS includes a successful identity result and no identity_error, alarms_error, or logs_error.
- When metric data exists, data_points contain timestamps and real values, not mock data.
- credential-status reports only booleans, never credential values.
- The Session finishes with stop_reason.type equal to end_turn.
- The summary does not equate empty results with overall health or CPUUser with total CPU.

Actual results from the final validation:

| Item | Tool evidence |
| --- | --- |
| Time | September 16, 2026, 15:46-15:47, Asia/Hong_Kong |
| Model | seed-2-0-lite-260428 |
| Skill | cloud-monitoring, version 2 |
| Credential presence | Four required variables present; session tokens not set |
| BytePlus CPUUser | 29 datapoints; 60-second averages; min 3.31%, max 3.69%, latest 3.47% |
| Latest sample | Unix timestamp 1789544760 |
| BytePlus alerts | Last 60 minutes; first-page data: []; total_count: null |
| AWS identity | GetCallerIdentity succeeded; root principal used in this test, unsuitable for a customer demo |
| AWS alarms | Empty returned regional ALARM MetricAlarms list |
| AWS logs | Empty returned matching-event list for the specified group and 60-minute window |
| Completion | All four script operations exited 0; Session ended with end_turn |

A 30-minute query returning 29 points does not establish complete coverage of every bucket. A null total_count does not mean there is exactly one page. The AWS adapter does not implement complete pagination or resource-specific alarm filtering. Matching logs are not all logs in the group.

### Step 7: Clean Up

After retaining sanitized evidence, confirm the IDs and delete only the dedicated test resources:

```bash
arkcli agent session delete <SESSION_ID> --yes --format json
arkcli agent env delete <ENVIRONMENT_ID> --yes --format json
```

Continue filtering reads to avoid exposing configuration if deletion failed:

```bash
arkcli agent session get <SESSION_ID> --format json --transform Result.Id
arkcli agent env get <ENVIRONMENT_ID> --format json --transform Result.Id
```

Both deletions succeeded in this test; subsequent get calls reported that the resources did not exist or were inaccessible. The Agent and Skill were retained. Monitored infrastructure was not modified.

Deleting MA resources **does not revoke cloud keys or establish immediate removal from internal backups or logs**. Revoke temporary credentials or rotate previously shared long-lived keys according to the customer's security requirements.

## 6. Complete Test History and Diagnosis

| Stage | Test | Observation | Supported conclusion |
| --- | --- | --- | --- |
| 1. Skill packaging and loading | Upload five-file ZIP, execute scripts, install boto3 and BytePlus SDK | Loading and installation succeeded; self-test returned synthetic=true, live_query=false | Skill execution works; live connectivity is not yet verified |
| 2. Missing credentials | Run a BytePlus query; add boolean-only credential-status | Credentials absent; live query failed; version 2 avoids printing environment values | Local SSO does not automatically supply monitoring credentials to MA |
| 3. Local credential control | Use original credentials locally for AWS STS and BytePlus metrics | STS succeeded; BytePlus returned 29 real points | Original credentials were valid at that time; this is not an MA success |
| 4. Vault environment variables | Inject the same credentials through a dedicated Vault | Variables present; AWS returned InvalidClientTokenId / UnrecognizedClientException; BytePlus returned InvalidAuthorization | These errors alone do not prove the original credentials expired |
| 5. Non-secret canary | Compare original SHA256/HMAC with sandbox calculations using a random value with no service access | Both comparisons failed for the Vault value | The tested Vault mode did not expose the original signing value to the local SDK |
| 6. HTTP echo control | Send canary headers/body to an echo service | HTTP 200; sandbox-observed echoes matched the sandbox value, not the original | Response-side remasking cannot be excluded; egress substitution is not conclusively established |
| 7. config.env canary control | Inject a non-secret value directly through Environment config.env | Original-value and HMAC comparisons passed; Vault comparisons still failed | config.env supports original-value injection and local signing in this environment |
| 8. Live config.env queries | Same Agent/Skill, dedicated Environment, real read-only calls to both clouds | BytePlus metrics/alerts and AWS identity/alarms/logs all succeeded | Direct Skill-based monitoring works without MCP |
| 9. Evidence and cleanup | Retain sanitized events; delete temporary credential-bearing resources | Deletes succeeded; resources no longer retrievable; five local regression tests passed | Test completed; original cloud credentials still require separate lifecycle management |

Two implementation mistakes were corrected during the investigation. An early Agent attempted unsafe environment inspection when real credentials were absent; version 2 added the boolean-only check. One canary probe mistakenly treated config.env as a filename; that invalid result was discarded, and subsequent controls read os.environ.

**Final diagnosis:** the limitation was not Skill support for cloud monitoring. Local SDK signing requires original AK/SK values, which the tested Vault path did not expose. The same Agent/Skill succeeded with config.env. This conclusion applies to the tested credential mode only; it does not establish that every Vault mode fails or fully characterize Vault's outbound substitution behavior.

## 7. Customer Demo Flow and Talk Track

Install dependencies, check permissions, and rehearse once before presenting. Do not enter credentials or display secret-bearing configuration while screen sharing.

1. Show the Agent's attached cloud-monitoring Skill and explain that no MCP server is configured.
2. Show the command entry point and SDK implementation; explain that execution takes place inside MA Cloud.
3. Submit approved resource IDs, time windows, and query objectives.
4. Show tool evidence: CPUUser datapoints, alert results, and log results.
5. Show the MA summary and verify its time scope, empty-result interpretation, and coverage limitations.
6. Show cleanup outcomes, without displaying configuration contents.

Suggested introduction:

> This demo packages AWS and BytePlus monitoring queries as a Skill that runs directly inside Managed Agents, without an additional MCP server. The Agent calls the cloud SDKs to retrieve real metrics, alarms, and logs, then summarizes the evidence. This demonstration validates the end-to-end query workflow; continuous scheduling, notifications, and remediation would be added separately based on customer requirements.

To demonstrate a visible alarm, obtain approval for dedicated test resources and clearly label simulated incidents. Do not induce a production failure. **This config.env validation did not create alarms or inject faults.**

## 8. Troubleshooting and Production Follow-Up

| Symptom | Next check |
| --- | --- |
| Skill loads but reports missing credentials | Verify the Session's Environment; expose only presence booleans |
| Variables exist but signing fails | Check credential type, expiry, session token, region, and injection mode; do not assume Skills are unsupported |
| AccessDenied | Check IAM for each actual operation; authentication success does not prove monitoring authorization |
| Empty metric data | Check resource, namespace, dimensions, time range, and collection status; do not interpret it as zero CPU |
| Empty alerts/logs | Report query scope and filters; expand the window only with approval; never fabricate incidents |
| Agent creation fails on InputSchema decoding | Prepare the Agent through the console and report CLI compatibility details |
| Model claims success despite a tool error | Use exit_code, ok, *_error, and returned data as the source of truth; correct the summary |

Production work remains: short-lived credential delivery and rotation, least-privilege IAM, egress controls, SDK error redaction, pagination and coverage, bounded retries/timeouts, scheduling, notification approval, auditing, and cost controls. Multiple Agents or Sessions do not replace these capabilities.

## 9. References and Handoff Checklist

- [MA Environment configuration](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/ModelArk/2553721): used during this investigation to confirm config.env configuration.
- [Detailed Skill validation notes](ma-monitoring-skill.md): English technical history with diagnostic Session references.
- This guide: customer demo workflow and complete investigation, without real account keys or customer resource parameters.
- Private sanitized events: retained for verification, not automatically bundled or published.

Before presenting: push the required code and documentation at a fixed commit, use a non-root least-privilege identity, obtain approval for test resources, rehearse live queries, inspect output redaction, and assign responsibility for cleanup.
