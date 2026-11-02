# Melo

Vue 3 + Electron 桌面对话工作台，Python FastAPI + Deep Agents 提供中文多轮对话。
开发版支持环境变量配置 OpenAI Chat Completions 兼容模型服务，纯文本、非流式；支持会话新建、切换、重命名、删除与重启恢复。消息和会话内虚拟文件由 Deep Agents / LangGraph 官方 SQLite checkpointer 持久化，不启用跨会话共享记忆。

## 启动

验证环境：Windows，Node 24.22.0 / npm 11.19.1，Python 3.13.13；后端支持 Python 3.12+。
已安装的准确依赖见 `desktop/package-lock.json` 和 `backend/uv.lock`。
核心版本：Electron 42.11.18、Deep Agents 0.7.32、FastAPI 0.162.0。

仓库只提供不含密钥的 `.env.example`，本地 `.env` 不提交。
启动前在 `backend/.env` 中填写模型服务的 `MODEL_BASE_URL`、`MODEL_API_KEY` 和 `MODEL_NAME`。
`MODEL_BASE_URL` 是服务商提供的 API 基础地址（如 `https://gateway.example/v1`），不要填完整的 `/chat/completions` 地址。
支持 HTTP(S) 地址，包括本机或局域网服务；远程服务建议使用 HTTPS。地址不能包含账号密码、查询参数或片段。
`MODEL_NAME` 填该服务实际支持的模型 ID；仅有地址和 Key 无法确定要调用哪个模型。
不要把模型 Key 填入 desktop/.env 或 VITE_*。

新检出项目时，先将 backend/.env.example 和 desktop/.env.example 分别复制为 .env，生成随机令牌（PowerShell `[guid]::NewGuid().ToString()`），将相同值填入两处 MELO_LOCAL_TOKEN。

先安装 Node.js 与 uv，并使用 Python 3.12+。检出仓库后安装依赖：

```powershell
cd backend
uv sync --frozen
cd ../desktop
npm ci
```

两个终端分别启动：

```powershell
# 终端一：在项目根目录
cd backend
uv run --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

```powershell
# 终端二：在项目根目录
cd desktop
npm run dev
```

后端缺少模型 Key 时仍能启动，页面会提示模型未配置；请修改 backend/.env 后重启后端，并点击页面右上角重新检查连接。
关闭 Electron 不会关闭单独启动的后端，终端按 Ctrl+C 停止。
端口 8000 必须空闲，不要将此服务直接暴露到公网。

## 验证

```powershell
cd backend
uv run ruff check .
uv run pytest
cd ../desktop
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:desktop
```

默认测试不调用付费模型。`test:desktop` 会启动实际 Electron 和只在测试使用的本地替身模型后端，使用临时数据库和独立空闲端口。
它验证真实 Deep Agents 图、IPC、两轮上下文、重置，以及后端停止/恢复后的输入保留和重试。截图在部分桌面会话不可用，不跳过功能断言。

真实模型测试会产生少量 API 消耗：配置 backend/.env 中的 MODEL_BASE_URL、MODEL_API_KEY、MODEL_NAME 后，在 backend 终端运行 `.venv/Scripts/python.exe -m tests.live_smoke`。它使用与应用相同的配置，不输出或保存密钥和对话正文。
手动重试可能再次计费；本地超时不保证上游停止生成。

## 结构与规范

LangSmith 指标监控已接入后端，默认关闭，只记录调用链、耗时、错误状态和 token 用量，隐藏对话正文。首次开通与本机配置见 [LangSmith 接入说明](docs/langsmith.md)。

- desktop/src/main：窗口、安全 IPC 和本地 HTTP；preload：仅暴露具名 health/会话管理接口。
- desktop/src/renderer：Vue 对话页；backend/app：验证、统一错误和 Deep Agents 运行。
- [产品决策](.trellis/spec/product/decisions.md)、[API 合同](.trellis/spec/guides/api-contract.md)、[测试](.trellis/spec/guides/testing.md)。
- [验证记录](docs/verification.md)。任务档案与个人会话日志只保留在本机。

保留 Trellis 0.6.17 的共享规范和工作流，使用 inline 模式；进入后续会话先读 AGENTS.md。
自动生成的工具脚本、平台配置、任务档案和个人日志不提交。需要 Trellis 开发流程时，在仓库根目录生成它们：

```powershell
npm install -g @mindfoldhq/trellis@0.6.17
trellis init --codex --skip-existing -u your-name
python .trellis/scripts/init_developer.py your-name
```
全局 hooks 和自动上下文注入未验证，手动读取规范即可开发。执行 `python .trellis/scripts/task.py list` 查看任务。

仓库：[llyb/Melo](https://github.com/llyb/Melo)，默认使用 main 分支。本轮没有配置或运行远程 CI。
本次不提供安装包、签名、云端部署、自动更新、模型切换或知识库。

## 本机 Obsidian

启用 [Obsidian Local REST API 插件](https://github.com/coddingtonbear/obsidian-local-rest-api)的原生 MCP。在 backend/.env 设置 `OBSIDIAN_MCP_ENABLED=true`、`OBSIDIAN_MCP_URL=https://127.0.0.1:27124/mcp/`、`OBSIDIAN_API_KEY`。自签名证书应从本机插件导出 PEM CA，将其绝对路径写入 `OBSIDIAN_CA_FILE`；不会关闭 TLS 验证或修改系统证书。修改配置后重启后端，左下角可重新检查连接。凭据只放后端，不能填入 renderer 或提交 Git。

Agent 仅获得列目录、读 Markdown、限量搜索、新建和更新五个工具。新建使用 create-only 条件；已有笔记的修改通过 Deep Agents 原生审批暂停，展示路径和差异，点击批准后才执行，并再次核对版本。插件缺少条件写能力时禁写；插件离线不影响普通聊天。虚拟文件属于会话，Obsidian 笔记属于真实 vault。

最多 5 个会话同时运行，同一会话一轮未决；审批等待不占运行名额。发送后立即清空输入，仍可编辑新草稿、新建、切换、左栏原位改名并点击 √ 保存。活动区展示真实模型/工具事件、连接心跳和审批状态，不展示模型隐藏推理正文。前台每秒轮询，后台或等待审批每 5 秒轮询。

已接受请求先落本地输入 outbox，再转为框架 checkpoint；关闭窗口不取消后端运行。后端重启后中断轮次需手动继续，不自动付费重发。每轮活跃预算 120 秒，审批等待不计入，最多 25 次图步进；预算耗尽需结束本轮。

外部笔记写入不会随回答失败、结束本轮或删除会话回滚。写入应答丢失时显示“待核对”：先在 Obsidian 核对对应路径，再接受当前状态或结束本轮；接受当前状态只记录核对，不宣称写入成功，也不重复执行。会话删除不删除 Obsidian 笔记。

## 会话和数据

数据保存在当前Windows用户的 `%LOCALAPPDATA%\Melo\data`，包含catalog.sqlite3（目录、请求引用、临时输入、受控事件及外部写回执）和checkpoints.sqlite3（框架状态）。catalog 自动由 v1 升级到 v2，保留原数据；回退旧代码前停止后端并恢复完整升级前备份，不能只回退一个数据库或期待撤销外部笔记。当前使用langgraph-checkpoint-sqlite 3.1.3；每会话独立thread_id，StateBackend文件工具不访问真实主机目录。只有完成轮次成为当前可见状态，失败分支可能仍在checkpoint中；删除会话会清理完整thread。

已提交消息和文件跨刷新、桌面/后端重启恢复；未发送草稿仅当前窗口保留。先停止后端再备份整个data目录（含存在的WAL/journal辅助文件）。本机数据未加密，不提供安全擦除、文件浏览器、云同步或跨会话记忆。模型窗口profile缺失时，使用原生摘要的12000 token触发/保留最近6条消息默认；更小窗口可能需要调整，错误不会推进成功会话状态。

桌面发送仅提交新增输入；旧POST /api/v1/chat保留为无状态兼容接口，不读写持久会话，旧39条/64000字符限制仅适用于该接口。手动重试已提交turn返回原回答；模型完成但未写checkpoint时重试仍可能再次计费。默认测试使用临时数据目录与空闲端口，不停止8000上的开发后端。
