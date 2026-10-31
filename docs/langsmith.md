# LangSmith 指标监控

已接入 Python 后端。监控包含 `Melo chat → Deep Agents → LLM` 调用链、起止时间、错误状态和模型返回的 token 用量。
根调用 ID 与 HTTP `request_id` / `X-Request-ID` 一致，便于关联本地错误。

按本次确认，只记录指标：SDK 隐藏所有层的输入和输出，异常文本替换为通用错误标记，metadata 仅保留请求 ID、模型标识和数字 token 用量。不记录对话正文、原始异常、环境变量或密钥。
模型没有返回 usage 时不伪造 token 数；此接入不配置评测、告警或自定义费用计算。

## 首次开通

1. 在 [LangSmith](https://smith.langchain.com) 注册或登录，选择美国区 workspace。
2. 打开 Settings → API Keys，创建有写入追踪权限的 API Key。若 Key 跨多个 workspace，将目标 workspace ID 一并填入配置。
3. 若界面显示 Agents：点击 **+ Agent → Observability**，名称 Melo、Agent ID `melo`，使用 `development` 环境。注册一次即可。
4. 若界面仍使用 Tracing Projects：创建名为 `melo` 的项目，使用下面的旧版项目配置。

新账号可能使用 agent-based workspace，不能只填旧版项目名。参见[官方接入说明](https://docs.langchain.com/langsmith/observability-quickstart)。

## 本机配置

只修改 `backend/.env`；它已被 Git 忽略。不要把 Key 发到聊天中，也不要写入 desktop/.env。

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=填入你的LangSmithKey
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=

# 新版 agent-based workspace
LANGSMITH_AGENT_ID=melo
LANGSMITH_AGENT_ENVIRONMENT=development
```

旧版项目 workspace 将 Agent ID 留空，并添加 `LANGSMITH_PROJECT=melo`。本应用在 Agent ID 非空时优先使用 Agent 地址，忽略项目名；不向同一次调用传入两种地址。
欧盟区将 endpoint 改为 `https://eu.api.smith.langchain.com`。自托管使用实例的 SDK API 地址。
当前进程环境变量优先于 `.env`；修改后必须重启后端。

`LANGSMITH_TRACING` 默认 `false`，只接受 true/false。开启时缺少 Key、项目名或端点无效会给出配置错误；关闭后不创建 LangSmith 客户端，错误的未启用地址也不会影响聊天。
隐藏正文是代码中的强制策略，不受全局 `LANGSMITH_HIDE_INPUTS/OUTPUTS` 设置影响。API Key 与模型 Key 分开配置。

## 验证

1. 按 README 启动后端及桌面端，发送一条不敏感的测试消息。
2. 打开 LangSmith 中的 Melo → Tracing → development；旧版打开项目 melo。
3. 找到 `Melo chat`，检查下级 Deep Agents 和 LLM 调用、耗时与 token；输入输出应为空。LangSmith 可能稍后才显示批量上传的数据。
4. 模型错误时应显示失败状态，但没有原始错误正文。监控上传失败只影响可观测性，不重试模型、不改变聊天结果；查看后端终端中的 LangSmith SDK 诊断。

若终端出现 `LangSmith monitoring disabled: SDK configuration error`，聊天仍可用，但监控未开启。检查并移除其他项目遗留的 `LANGSMITH_RUNS_ENDPOINTS`，不要与本应用的单一 endpoint 配置混用，然后重启后端。

每次对话在后台批量上传，正常关闭后端时最多等待 2 秒清理队列。强制终止或网络中断可能丢失尚未上传的监控数据，聊天记录不会因此持久化到本机。

关闭监控：`LANGSMITH_TRACING=false`，重启后端。

## 已完成的本地检查

`uv run pytest tests/test_monitoring.py -q` 用真实 LangSmith SDK 的直传和 JSON 批量路径、离线 HTTP Session 检查：隐藏正文/凭据/原始异常、保留用量及调用父子关系、请求 ID 关联、新旧 workspace、关闭开关、上传失败和退出清理。另用真实 ChatOpenAI 兼容客户端配合离线响应检查模型序列化与 usage 提取。
默认测试不需要 Key、不访问外网。未提供 LangSmith Key 时，不代表真实云端已接通；完成账户配置后仍需按上面的步骤进行一次云端验收。

实现依据：[显式 tracing context](https://docs.langchain.com/langsmith/trace-without-env-vars)、[隐藏敏感数据](https://docs.langchain.com/langsmith/mask-inputs-outputs)。

## 本机云端验收（2026-10-30）

已使用实际 FastAPI → Deep Agents → Z.AI glm-5.3 调用进行云端回读验证，目标为 melo / local。一次模型调用产生 12 个追踪节点，输入 39、输出 8，共 47 tokens；全部完成且成功，所有节点的输入/输出正文为空，未发现本机凭据值。

实际云端使用新查询接口读取；旧 read_run(load_child_runs=True) 不适用于当前存储后端。云端返回的 run_type/status 按实际值判断。查看链接仅保存在被忽略的本机 .tools 验证结果中，不写入共享仓库。
