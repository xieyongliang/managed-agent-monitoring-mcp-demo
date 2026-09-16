# Monitoring Skill inside MA Cloud

## Architecture

MA loads a custom Skill, uses built-in Bash to run its bundled Python script,
and summarizes structured results. There is no MCP server or external executor.
The script reuses `tools.py` (AWS) and `byteplus_tools.py` (BytePlus).

The archive contains only five allowlisted source files. It contains no cloud
credentials, local configuration, virtual environment, or MCP dependency.

**Latest validation (2026-09-16):** Real AWS and BytePlus read-only API queries
succeeded inside MA Cloud with Skill version 2 and credentials injected through
Environment `config.env`. No MCP server was used. See the config.env live test
below for results, security limits, and cleanup.

## Build and attach

From the repository root:

```bash
python build_monitoring_skill.py --output /tmp/cloud-monitoring-skill.zip
arkcli agent skill create --zip /tmp/cloud-monitoring-skill.zip --format json
```

Attach the returned custom Skill ID and version to an MA Agent with Bash/read
enabled and no MCP servers. Create a Cloud Session with outbound networking.
Ask it to load `cloud-monitoring` and execute:

```bash
python /mnt/skills/cloud-monitoring/scripts/monitor.py credential-status
python /mnt/skills/cloud-monitoring/scripts/monitor.py self-test
```

For live queries, install `scripts/requirements.txt`, then use the commands in
the bundled SKILL.md with operator-provided resource IDs and log groups.
The AWS adapter reads alarms/logs; it does not yet query AWS metrics.

## Credentials

BytePlus SSO authorizes local ArkCLI management operations; it does not inject
AWS or BytePlus Cloud Monitor credentials into a Session. An AWS EC2 role on
the original MCP host is not inherited by MA either.

Provision least-privilege, preferably temporary cloud credentials through an
approved runtime secret-delivery mechanism. This example does not implement
that mechanism. Do not put keys in the Skill ZIP, system prompt, chat messages,
setup-script source, Git history, or test logs. Do not assume an MCP Vault bearer
credential automatically becomes the signing credentials required by cloud SDKs.

`credential-status` prints only environment-variable presence booleans. It does
not resolve AWS profile/role credentials. Never use `env` or `printenv` to inspect
secrets. A script running inside the sandbox can access its runtime credentials;
use an external constrained executor if this trust boundary is unacceptable.

## Cloud validation on 2026-09-16

- Agent: `agent-20260916065112-mhfg5`, model `seed-2-0-lite-260428`.
- Skill: `skill-20260916064035-gvchh`.
- Environment: `env-20260915154146-wzwvk`, cloud, unrestricted networking.
- First Session: `sesn-20260916065120-ljdmk`, Skill version 1.
- Skill mounted at `/mnt/skills/cloud-monitoring/`.
- Dependency install succeeded, including boto3 and BytePlus SDK 3.0.60.
- Self-test exited 0 and explicitly returned synthetic=true, live_query=false.
- BytePlus ListAlertGroup path exited 1 before a signed API request because
  runtime credentials were absent. No real cloud monitoring data was retrieved.
- Session finished with `end_turn`; no MCP was configured or called.

During version 1 testing the model used an unsafe environment-inspection command.
The variables were absent, so no credential values were exposed. Version 2 adds
the boolean-only `credential-status` command and explicit guidance against
printing environment variables. This reduces accidental exposure; instructions
are not a security isolation boundary.

Version 2 validation Session: `sesn-20260916065355-lzl94`. Credential-status and
synthetic self-test both exited 0. The credential check returned booleans only,
all false, and the Session finished with `end_turn`. No dependency installation
was necessary for these two commands. No live queries were run in this Session.

**Conclusion at this stage:** Skill loading and local script execution inside MA Cloud are
verified. Direct signed AWS/BytePlus API queries from this Skill have not
yet succeeded. The later config.env live test below resolves this limitation.
Prior successful MCP tests are not evidence of live Skill queries.

## Live-query attempt with Vault environment variables

Session: `sesn-20260916070100-99sj9`, same Agent version 2 and Skill version 2.
Test window: 2026-09-16 15:01-15:03 Asia/Hong_Kong. No MCP was configured.

Before deployment, the same original credentials were checked locally:

- AWS STS GetCallerIdentity succeeded. This verifies credential validity, not
  all CloudWatch/log permissions.
- BytePlus GetMetricData succeeded with 29 CPUUser datapoints for the test ECS
  instance. Values ranged from 3.43% to 3.80%, latest 3.59% at epoch 1789541940.
  This is local control evidence, not an MA query result.

A dedicated Vault was created with four `environment_variable` credentials and
attached to the new Session. Values were passed through CLI stdin, not stored
in the Skill, prompts, repository, or local credential files. The test used
unrestricted credential networking; this is not a production recommendation.

| Check inside MA | Result |
| --- | --- |
| SDK installation | Succeeded |
| Four credential environment variables | Present |
| BytePlus GetMetricData | Exit 1, InvalidAuthorization |
| BytePlus ListAlertGroup | Exit 1, InvalidAuthorization |
| AWS GetCallerIdentity / DescribeAlarms | InvalidClientTokenId |
| AWS FilterLogEvents | UnrecognizedClientException |
| AWS access-key format check | False for AKIA/ASIA + 16 uppercase alphanumeric characters |
| BytePlus access-key prefix check | False for the supplied AKAP prefix |

BytePlus request IDs:

- GetMetricData: `20260916070210EFD23784CEBD71A72A46`
- ListAlertGroup: `20260916070214B12CF65049FAC0D504EF`

Format diagnostics emitted booleans only, not secret values or hashes. These
results show that presence is insufficient: the access-key values visible to
the sandbox did not match the original key formats. Vault placeholder/substitution
behavior is a hypothesis requiring platform confirmation, not a proven corruption
bug. The original credentials must not be declared expired from these errors.
Missing session tokens alone do not invalidate static key pairs.

The cloud APIs returned authentication errors, so this was not a simple network
timeout. No live monitoring data was obtained inside MA. The Agent initially
misattributed the errors to expired credentials; use the tool events and local
control results rather than that unsupported summary.

At 15:04 all four test Vault credentials were deleted, the empty list was
verified, and the dedicated Vault was deleted. This does not rotate or revoke
the original cloud keys. Session history was retained for diagnosis.

The next integration requirement is a documented MA mechanism for SDK signing:
either supported raw temporary credential injection into the execution runtime,
or a constrained external signer/executor. Do not work around Vault protection
by placing long-lived keys in Skill source, setup scripts, or model messages.

## Synthetic Vault substitution experiment

A follow-up test used a random canary with no access to any service, not a real
cloud key. Vault networking was restricted to httpbin.org. Only expected SHA256
and HMAC digests, never the original canary, were provided to the sandbox probe.

Session: `sesn-20260916072427-5wnsc`.

| Observation | Result |
| --- | --- |
| Vault variable present | true |
| Local SHA256 equals original canary SHA256 | false |
| Local HMAC equals original canary HMAC | false |
| Non-Vault control header/body round trip | true / true |
| Bearer header echo matches original / sandbox value | false / true |
| X-Api-Key header echo matches original / sandbox value | false / true |
| JSON body echo matches original / sandbox value | false / true |
| Echoed signature equals sandbox HMAC / original HMAC | true / false |

All five HTTP requests returned 200. This proves the sandbox does not see the
original Vault value and computes a different HMAC. It does NOT conclusively
prove outbound substitution: an echo observed inside the sandbox cannot rule
out response-side re-masking. To distinguish no outbound replacement from
bidirectional masking, use an independently observed server-side digest or a
server-side equality check that returns only a boolean.

The supplied quickstart links to the official environment configuration page:
https://ai.byteplus.com/ark/region:ap-southeast-1/docs/ModelArk/2553721
That page explicitly documents `config.env` for environment-variable injection,
separately from Vault, and `config.packages` for cached dependencies. The
quickstart's client-side ARK_API_KEY export is not sandbox credential injection.
Environment configuration is retrievable through the API: ordinary config.env
must not be assumed to provide the same confidentiality boundary as Vault.

### Direct environment control

Session `sesn-20260916072724-w7xds` used environment
`env-20260916072714-m7z2v` with a second synthetic canary in `config.env`, while
also attaching the test Vault. At 15:29:15 the corrected probe returned:

```text
MA_DIRECT_CANARY: present=True matches_original=True hmac_matches_original=True
MA_VAULT_CANARY: present=True matches_original=False hmac_matches_original=False
```

The first generated probe mistakenly treated the API field `config.env` as a
disk filename; that invalid control result was discarded. The corrected probe
read both values using os.environ, with no file-based credential lookup.

This verifies that ordinary config.env supports original-value injection and
local HMAC, whereas the tested Vault mode does not expose the original value to
the sandbox. No real cloud keys were used in this experiment. It still does not
establish exactly which HTTP fields are substituted at egress. The synthetic
Vault credential and Vault were deleted after testing; the non-secret control
environment and Session history were retained.

For a subsequent cloud-query test, prefer narrowly scoped temporary credentials
and explicitly assess the visibility/retention of environment configuration.
Do not turn the control result into a recommendation to store long-lived keys
in ordinary environment configuration.

## Live query with config.env: successful

Test window: 2026-09-16 15:46-15:47 Asia/Hong_Kong.

- Agent: `agent-20260916065112-mhfg5`, version 2.
- Skill: `skill-20260916064035-gvchh`, version 2.
- Temporary Environment: `env-20260916074623-lhltp` (deleted after testing).
- Temporary Session: `sesn-20260916074628-7db49` (deleted after testing).
- Evidence event: `sevt-20260916074724-zth8x` (sanitized local copy retained).
- Model: `seed-2-0-lite-260428`. No Vault or MCP attached.

With explicit operator approval, the test injected the four cloud credential
variables via Environment `Config.Env`. This is an API configuration field,
not a file named config.env. A private driver accepted credentials through
non-echoed stdin, passed the Environment payload through CLI stdin, and captured
secret-bearing create responses without printing or persisting them. Credentials
were never included in the Skill archive, source code, or Agent messages.

Reproduction sequence:

1. Build and upload the Skill as described above; attach it to an Agent with
   built-in Bash and no MCP servers.
2. Create a dedicated cloud Environment with unrestricted outbound networking
   and `Config.Env` containing `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `BYTEPLUS_ACCESS_KEY`, and `BYTEPLUS_SECRET_KEY`. Include session tokens
   when using temporary credentials. Send the structured payload over stdin;
   do not echo the create/get responses because they can contain these values.
3. Create a Session using that Environment and the Skill-enabled Agent.
4. Install the bundled requirements, run `credential-status`, then run
   `byteplus-metric`, `byteplus-alerts`, and `aws-context` with your resource
   IDs, region, and log group. The bundled SKILL.md describes the JSON arguments.
   Wrap execution with bounded timeouts and credential-value redaction for
   stdout/stderr. Do not run `env`, `printenv`, or inspect credentials in chat.
5. Check actual tool results, not just the model's summary. Save only sanitized
   evidence. Delete the temporary Session and Environment after the test.

Observed tool results:

| Operation | Actual result |
| --- | --- |
| Credential presence check | Four required variables present; values not printed |
| BytePlus GetMetricData | Success; 29 CPUUser datapoints, 60-second average, range 3.31%-3.69%, latest 3.47% |
| BytePlus ListAlertGroup | Success; first page data empty, total_count null |
| AWS STS GetCallerIdentity | Success |
| AWS CloudWatch DescribeAlarms | Success; returned ALARM metric-alarm list empty |
| AWS CloudWatch Logs FilterLogEvents | Success; returned matching log-event list empty |

All four script operations exited 0. The Session finished with `end_turn`.
BytePlus CPUUser covered a rolling 30-minute query, with latest returned sample
at epoch 1789544760. This is user-mode CPU, not total CPU. The results do not
establish complete coverage of every bucket up to query end. BytePlus alerts
covered a 60-minute query and one page only. AWS alarms were regional and not
filtered to the EC2 instance; logs covered the specified log group, 60-minute
window, and the script's error filter. AWS CPU metrics were not queried. Empty
results are not proof of resource health.

This confirms Skill-based monitoring works without an MCP server when the SDK
can access original signing credentials. Compared with the earlier Vault test,
the same Agent/Skill succeeds using config.env. The tested Vault path changed
the sandbox-visible value, making local HMAC signing differ from signing with
the original secret. This does not establish the full Vault egress substitution
contract or imply all Vault authentication modes fail.

Cleanup calls succeeded for both temporary resources, and subsequent get calls
reported that they did not exist or were inaccessible. Original cloud keys were
not revoked by this cleanup, and service-internal retention was not assessed.
Ordinary config.env is readable configuration, not a secret vault. Use this as
an explicitly approved test approach, not a default production secret store.
The AWS identity in this test was root; replace it with least-privilege temporary
credentials before further use, and rotate previously shared long-lived keys.

## Local regression tests

```bash
python -m unittest test_monitoring_skill.py test_byteplus_tools.py
```

These cover standalone ZIP execution, the exact package allowlist, explicit
synthetic labeling, credential-status redaction, missing-credential failure,
input validation, and BytePlus SDK request construction. They make no real cloud
calls. Existing MCP behavior remains available separately.

## CLI compatibility observed

The installed CLI's high-level Agent create command failed while decoding
ListAgents: InputSchema was an object but the client expected a string.
Creation used the registered `managed_agent.create_agent` API after preview and
confirmation. Agent get, Session creation, Skill upload/update and `+iterate`
worked. Streaming commands require `--format jsonl`, not bounded `--format json`.
