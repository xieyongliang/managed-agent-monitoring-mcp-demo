# MA Cloud + Skill + config.env：AWS 与 BytePlus 监控 Demo

实测日期：2026-09-16。适用对象：客户技术团队、解决方案团队、演示人员。

[English version](ma-monitoring-skill-config-env-demo.en.md)

## 1. Demo 目标与结论

本示例让 ModelArk Managed Agent（MA）在云端加载自定义监控 Skill，通过内置 Bash 执行 Python SDK，直接读取 AWS 和 BytePlus 监控信息，再根据实际结果生成摘要。

**本次已经跑通真实云端查询，不需要部署 MCP Server，也不需要客户电脑充当执行器。**

| 实测能力 | 结果 |
| --- | --- |
| MA 加载自定义 Skill、执行 Python | 成功 |
| 通过 Environment `config.env` 提供 SDK 签名凭据 | 成功 |
| BytePlus ECS CPUUser 指标 | 成功，返回 29 个真实数据点 |
| BytePlus 告警历史 | 查询成功，本次返回空列表 |
| AWS 身份验证、CloudWatch 告警和日志 | 查询成功，本次告警和匹配日志为空 |
| MA 根据工具结果生成摘要 | 成功，Session 以 `end_turn` 结束 |
| 删除临时 Session 与 Environment | 成功，删除后回查不可获取 |

这是一次**按需执行、只读查询**的端到端 Demo。当前没有持续轮询调度、自动通知、自动修复，也未证明生产环境的长期可靠性。复现应得到相同的查询流程，不应期待不同时刻出现相同的指标数值。

## 2. 架构与职责

```text
操作人员 / ArkCLI
  │ 上传 Skill，配置 Agent，创建 Environment 和 Session
  ▼
MA Cloud Session
  ├─ 主模型：理解监控任务、调用工具、整理证据
  ├─ 自定义 Skill：操作说明 + Python 监控脚本
  ├─ 内置 Bash：在 MA 云端执行脚本
  └─ Environment config.env：提供本次测试的运行时凭据
       │
       ├─ boto3 → AWS STS / CloudWatch / CloudWatch Logs
       └─ BytePlus SDK → Cloud Monitor
  │
  ▼
结构化查询结果 → MA 输出监控摘要与查询范围说明
```

- **Skill**：代码和使用说明的分发方式，不是独立服务，也不是调度器。
- **MA**：运行模型与脚本的云端执行环境。
- **SDK**：读取运行时凭据，在本地计算签名并通过 HTTPS 调用云 API。
- **ArkCLI**：用于管理和操作 MA 资源；本机登录状态不会自动变成云端 SDK 的凭据。
- **config.env**：Environment 配置中的环境变量映射，**不是一个名叫 `config.env` 的磁盘文件**。

本次数据请求由 MA 云端发出，不经过先前部署的 MCP EC2 主机。MCP 仍然可以作为集中权限控制和共享工具服务的另一种架构，但不是这个 Demo 的前提。

## 3. 代码组成

代码仓库：[managed-agent-monitoring-mcp-demo](https://github.com/xieyongliang/managed-agent-monitoring-mcp-demo)。仓库名称保留了历史上的 MCP 实现；本文描述的是其中的 Skill 路径。

> 版本提示：本文与 Skill 实现一起维护。演示前请拉取包含这些文件的版本，记录用于演示的 commit，并从干净 checkout 验证打包。

| 文件 | 用途 |
| --- | --- |
| `build_monitoring_skill.py` | 用白名单构建 Skill ZIP |
| `skills/cloud-monitoring/SKILL.md` | MA 读取的监控操作指南 |
| `skills/cloud-monitoring/scripts/monitor.py` | 统一命令入口 |
| `skills/cloud-monitoring/scripts/requirements.txt` | SDK 依赖 |
| `tools.py` | AWS 查询实现，打包时放入 Skill |
| `byteplus_tools.py` | BytePlus 查询实现，打包时放入 Skill |
| `test_monitoring_skill.py`、`test_byteplus_tools.py` | 本地回归测试 |

ZIP 只包含以下五个文件，不包含密钥、配置文件、虚拟环境或 MCP Server：

```text
cloud-monitoring/
  SKILL.md
  scripts/
    monitor.py
    requirements.txt
    tools.py
    byteplus_tools.py
```

## 4. 演示前准备

### 4.1 账号与网络

1. BytePlus 账号已开通 MA，ArkCLI 已安装并完成授权。
2. 本次使用 BytePlus `ap-southeast-1` 的 MA 配置；不要混用其他产品的账号或 API 地址。
3. 选择账号中可用的 MA 模型。本次实测模型为 `seed-2-0-lite-260428`。
4. MA Environment 可以访问所需的依赖仓库和 AWS、BytePlus API。本次配置为 unrestricted；生产环境应另行评估出站限制。
5. 准备 AWS 日志组、目标区域和资源 ID，以及 BytePlus 有监控数据的 ECS 资源 ID。

以下命令在仓库根目录执行。先确认身份和配置：

```bash
arkcli auth status --format json
arkcli profile show --format json
arkcli agent model list --format json
```

账号未开通或认证过期时，应先解决认证和开通问题，不能通过更换凭据类型绕过。

### 4.2 区分三类凭据

| 凭据 | 用途 | 是否能代替云监控 AK/SK |
| --- | --- | --- |
| BytePlus SSO | ArkCLI 管理 MA 资源 | 否 |
| ModelArk API Key | MA 数据面等相应 API 调用 | 否 |
| AWS / BytePlus 云 AK/SK及可选 Session Token | SDK 签名访问对应云资源 | 是，本 Demo 需要的是这一类 |

使用最小权限、优先短期有效的凭据。AWS 查询涉及 `GetCallerIdentity`、`DescribeAlarms`、`FilterLogEvents`；BytePlus 涉及 `GetMetricData`、`ListAlertGroup`。具体 IAM 策略由客户管理员按实际服务、资源与组织策略配置，本文不提供未经验证的通用策略。

**安全边界：**普通 `config.env` 是可通过配置接口读取的数据，不是专用密钥存储。能执行脚本的 Agent 也可以访问这些环境变量。禁止把密钥写进 Skill、系统提示词、聊天、setup script、Git 或演示截图。不要使用 root 凭据做客户 Demo；本次测试中发现 AWS 身份为 root，后续必须替换。

## 5. 复现流程

### 第一步：本地验证与打包

```bash
python3 -m unittest test_monitoring_skill.py test_byteplus_tools.py
python3 build_monitoring_skill.py --output /tmp/cloud-monitoring-skill.zip
arkcli agent skill create --zip /tmp/cloud-monitoring-skill.zip --format json
```

记录返回的 Skill ID 和版本。本次本地回归测试共 5 项通过；这些测试不调用真实云 API，不能代替后面的云端验证。

### 第二步：配置 Agent

在 MA 控制台创建或选择专用演示 Agent：

- 选择当前账号可用模型，本次实测使用 `seed-2-0-lite-260428`。
- 挂载上一步上传的自定义 Skill，固定到已验证版本。
- 确保内置 Bash/read 可用，不配置 MCP Server。
- 使用以下系统指令，并记录 Agent ID 和版本：

```text
Use the cloud-monitoring skill and built-in bash/read tools for read-only
monitoring. Never use MCP or expose credentials. Distinguish synthetic tests,
partial queries and live evidence. Do not modify infrastructure.
```

系统指令用于约束行为，不是权限隔离。真正的只读边界来自云端 IAM 权限。

本次 CLI 的高层 Agent 创建流程曾遇到 ListAgents 的 InputSchema 解码兼容性错误，实际测试复用了已创建的 Agent。客户演示建议提前创建和验证 Agent；若遇到该错误，使用控制台创建并反馈 CLI 兼容性问题，而不是改用其他云账号。

### 第三步：通过 config.env 创建专用 Environment

下列结构用于说明配置，**其中占位符不是真实凭据，不能直接用于查询**：

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

短期凭据还需要相应的 `AWS_SESSION_TOKEN` 或 `BYTEPLUS_SESSION_TOKEN`。不要把真实配置保存到仓库或终端历史；不要直接展示 create/get 的完整响应，响应可能包含原值。

下面是与本次驱动方式一致的最小创建示例：交互输入不回显，通过 stdin 发送 JSON，捕获响应后只显示 ID。此示例用于正常交互终端，不要开启 shell tracing、调试日志或录屏。创建超时后应先在控制台按唯一名称确认结果，不要盲目重试创建。

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

本次实测由私有驱动执行了上述相同的配置和 stdin/capture 模式。这里的交互输入示例不是额外一次云端测试，也不实现生产级凭据管理或自动清理。

### 第四步：创建 Session

用实际 ID 替换以下占位符，只输出 Session ID，避免显示解析后的环境配置：

```bash
arkcli agent session create \
  --agent-id <AGENT_ID> \
  --agent-version <AGENT_VERSION> \
  --environment-id <ENVIRONMENT_ID> \
  --title "arkcli-monitoring-skill-demo" \
  --format json --transform Result.Id
```

如果当前 CLI 的结构与 `Result.Id` 不一致，不要去掉过滤后直接展示响应；应使用捕获输出的驱动解析 `Result.Id` 或顶层 `id`。本次实测使用驱动捕获完整响应并只输出 ID。

### 第五步：让 MA 执行真实查询

在 Session 中发送以下任务，先将资源占位符换为客户批准使用的测试资源。资源 ID、日志组可以作为任务参数；密钥不可以。

```text
请使用 cloud-monitoring Skill 完成一次真实只读监控查询，不使用 MCP。
先读取 SKILL.md，再安装 scripts/requirements.txt。
凭据已通过 Environment config.env 注入，禁止打印任何密钥或运行 env/printenv。
只允许用 credential-status 查看环境变量是否存在。

查询区域：ap-southeast-1。
BytePlus：ECS <BP_ECS_ID>，最近 30 分钟 CPUUser，最近 60 分钟告警历史。
AWS：资源 <AWS_RESOURCE_ID>，日志组 <AWS_LOG_GROUP>，最近 60 分钟匹配日志，
并查询区域内 ALARM 状态的监控告警。

通过 Python subprocess 执行 Skill 命令，每个命令限制 70 秒。
捕获 stdout/stderr，将其中与凭据环境变量原值相同的内容替换为 [REDACTED]
后再输出。安装依赖限制 90 秒。不要输出未过滤的 SDK 错误。

仅根据真实工具结果总结，不使用 self-test 代替真实查询。
报告查询范围、时间窗口、返回数量、错误和未覆盖内容。
CPUUser 不是总 CPU；告警/日志为空不代表资源健康。
AWS 告警需核对维度后才能归属具体资源。本脚本不查询 AWS CPU 指标。
查询完立即停止，不修改云资源、不发送通知。
```

也可以用 ArkCLI 发送不含密钥的任务并等待结果：

```bash
arkcli agent session events send <SESSION_ID> \
  --text "<上述已经填好资源参数的任务>" \
  --poll --wait-timeout 300 --format jsonl
```

提示词中的脱敏要求不是可靠的安全隔离。本次为减少自由发挥，给 MA 提供了确定的 Python wrapper：捕获四个子进程的输出，按六个凭据环境变量的非空值进行替换，再打印结构化结果，并设置每条命令 70 秒超时。仍应使用低权限凭据，控制日志访问，演示前检查事件内容。

以下是 wrapper 内调用的命令，**应在 MA 中执行，而不是在客户本机执行后冒充 MA 结果**：

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

### 第六步：验收结果

不要只看 Agent 最终回复。检查 Session 工具事件中的以下字段：

- 各操作 `exit_code` 为 0，BytePlus 返回 `ok: true`。
- AWS 结果包含成功 identity，且没有 `identity_error`、`alarms_error` 或 `logs_error`。
- 指标真实存在时，返回包含时间戳的 `data_points`，不是 mock 数据。
- `credential-status` 只显示布尔值，不出现凭据原值。
- Session 正常结束，`stop_reason.type` 为 `end_turn`。
- 最终摘要没有把空结果解释为全部健康，未把 CPUUser 解释成总 CPU。

本次最终实测记录：

| 项目 | 工具返回事实 |
| --- | --- |
| 时间 | 2026-09-16 15:46–15:47，Asia/Hong_Kong |
| MA 模型 | `seed-2-0-lite-260428` |
| Skill | cloud-monitoring，版本 2 |
| 凭据存在性 | 四个必需环境变量均为 true；未设置 Session Token |
| BytePlus CPUUser | 29 点，60 秒平均值，最小 3.31%，最大 3.69%，最新 3.47% |
| 最新样本时间 | Unix timestamp `1789544760` |
| BytePlus 告警 | 最近 60 分钟，第一页 `data: []`，`total_count: null` |
| AWS 身份 | GetCallerIdentity 成功；测试身份为 root，不适用于客户 Demo |
| AWS 告警 | 区域内 ALARM 状态 MetricAlarms 返回空列表 |
| AWS 日志 | 指定日志组、最近 60 分钟、脚本匹配条件返回空列表 |
| 退出状态 | 四个脚本操作均 exit 0，Session 为 end_turn |

注意：30 分钟查询得到 29 个点不等于已经证明整个窗口每个桶都完整。告警 `total_count` 为 null 也不能写成“共一页”。AWS 脚本没有实现完整分页遍历或实例维度告警筛选；匹配日志也不代表该日志组的全部日志。

### 第七步：清理

保存脱敏证据后，只删除本次专用资源。确认 ID 正确再执行：

```bash
arkcli agent session delete <SESSION_ID> --yes --format json
arkcli agent env delete <ENVIRONMENT_ID> --yes --format json
```

回查时继续过滤配置，避免删除失败时显示明文：

```bash
arkcli agent session get <SESSION_ID> --format json --transform Result.Id
arkcli agent env get <ENVIRONMENT_ID> --format json --transform Result.Id
```

本次删除请求成功，随后两个 get 均返回“资源不存在或无权访问”。Agent 和 Skill 保留，未修改被监控的业务资源。

删除 MA 资源**不等于撤销云 AK/SK，也不证明平台内部备份或日志立即清除**。按客户安全要求撤销临时凭据或轮换已分享的长期密钥。

## 6. Skill 与 config.env 测试过程

| 阶段 | 做了什么 | 观察结果 | 可以得出的结论 |
| --- | --- | --- | --- |
| 1. Skill 打包及加载 | 上传五文件 ZIP，在 MA 运行脚本、安装 boto3 和 BytePlus SDK | 加载及依赖安装成功；self-test 返回 synthetic=true、live_query=false | MA 能运行 Skill；尚未验证真实查询 |
| 2. 无凭据测试 | 调用 BytePlus 查询；增加布尔型 credential-status | 凭据不存在，真实查询失败；版本 2 不再要求输出环境变量内容 | 本机 SSO 不会自动给 MA 提供云监控凭据 |
| 3. 本机凭据对照 | 在本机用原始凭据做 AWS STS 和 BytePlus 指标查询 | STS 成功；BytePlus 返回 29 个真实数据点 | 原始凭据在当时有效；不等于 MA 查询成功 |
| 4. config.env canary 验证 | 将无权限测试值直接放入 Environment config.env | 原值比对成功、HMAC 比对成功 | config.env 在本次环境中支持原值注入和本地签名 |
| 5. config.env 真实查询 | 使用专用 Environment 和挂载 Skill 的 Agent，执行双方真实只读 API | BytePlus 指标、告警与 AWS 身份、告警、日志均查询成功 | Skill 直接访问云监控的链路已跑通，不依赖 MCP |
| 6. 证据与清理 | 保留脱敏工具事件，删除含凭据的测试 Session/Environment | 删除成功，回查不可获取；本地 5 项回归测试通过 | 实验闭环完成，但原始云凭据仍需独立管理 |

测试期间还纠正了两类问题：早期 Agent 尝试了不安全的环境变量检查方式，当时没有注入真实凭据；版本 2 增加了布尔型检查。一次 canary 探针误把 `config.env` 当成文件名，该无效结果已丢弃，后续对照均从 `os.environ` 读取变量。

**测试结论：**通过 config.env 提供运行时凭据后，MA 内的 Skill 可以使用 SDK 完成本地签名，直接查询 AWS 和 BytePlus 的真实监控数据，不需要额外部署 MCP Server。

## 7. 客户演示顺序与话术

建议在客户到场前完成依赖安装、权限检查和一次预演，避免现场等待授权；不要在共享屏幕时输入或展示密钥配置。

1. 展示 Agent 挂载的 cloud-monitoring Skill，说明没有 MCP Server。
2. 展示 Skill 的指令入口和 SDK 代码，说明执行发生在 MA 云端。
3. 输入客户批准的资源 ID、时间窗口与查询目标。
4. 展示工具返回的 CPUUser 时间序列、告警和日志结果。
5. 展示 MA 摘要，并核对时间范围、空结果含义与查询限制。
6. 展示临时资源清理结果，不展示配置原文。

可直接使用的介绍：

> 这个 Demo 把 AWS 和 BytePlus 的监控查询封装为一个 Skill，直接运行在 Managed Agent 的云端环境里，不需要额外部署 MCP 服务。Agent 会调用云厂商 SDK 获取真实指标、告警和日志，再根据结果整理摘要。这次主要验证的是监控查询的端到端链路，持续调度、通知和自动处置可以在后续按客户需求补充。

若要展示明确的告警，不应等待生产故障或制造生产异常。可以另行申请专用测试资源与模拟告警，但必须明确标注模拟数据；**本次 config.env 实测没有新建告警，也没有主动制造故障**。

## 8. 常见问题与下一步

| 情况 | 处理方式 |
| --- | --- |
| Skill 能加载，但查询提示缺少凭据 | 检查当前 Session 引用的 Environment；只显示 presence 布尔值 |
| 变量存在但签名失败 | 检查凭据类型、有效期、Session Token、区域与注入方式；不要直接认定 Skill 不支持 |
| 查询返回 AccessDenied | 根据实际 API 操作核对 IAM，不能把认证成功等同于所有监控权限都具备 |
| 指标为空 | 检查资源 ID、命名空间、维度、时间窗口与监控采集状态；不要当成 CPU 为零 |
| 告警或日志为空 | 报告范围和过滤条件；必要时经客户批准扩展窗口，不得编造告警 |
| 高层 Agent 创建出现 InputSchema 解码错误 | 提前通过控制台准备 Agent，并反馈 CLI 兼容性问题 |
| 工具返回失败，但模型说查询成功 | 以实际 exit code、ok、*_error 和原始数据为准，修正摘要 |

生产化还需要独立设计：短期凭据发放与轮换、最小权限与网络策略、SDK 错误脱敏、分页和查询覆盖、超时重试、持续调度、通知审批、审计与费用控制。多 Agent 和多 Session 本身不能代替这些能力。

## 9. 参考与交付清单

- [MA Environment 配置文档](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/ModelArk/2553721)：本次用于确认 config.env 的配置方式。
- [英文客户指南](ma-monitoring-skill-config-env-demo.en.md)：对应的 Skill + config.env 演示文档。
- 本文：客户演示流程与 Skill + config.env 测试经过，不包含实际账号密钥或客户资源参数。
- 私有脱敏事件：本次保留用于复核，不默认打包或提交到公开仓库。

对外演示前确认：代码和文档已推送到固定 commit、使用非 root 最小权限凭据、测试资源已批准、真实查询已预演、输出已做脱敏检查、清理责任人已明确。
