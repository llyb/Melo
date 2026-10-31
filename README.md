# Melo

Vue 3 + Electron 桌面对话工作台，Python FastAPI + Deep Agents 提供中文多轮对话。
开发版支持通过环境变量配置 OpenAI Chat Completions 兼容模型服务；纯文本、非流式，历史仅保留在当前窗口内存。关闭、刷新或新建会话后清空。

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

默认测试不调用付费模型。`test:desktop` 会启动实际 Electron 和只在测试使用的本地替身模型后端；请先停止占用 8000 的开发后端。
它验证真实 Deep Agents 图、IPC、两轮上下文、重置，以及后端停止/恢复后的输入保留和重试。截图在部分桌面会话不可用，不跳过功能断言。

真实模型测试会产生少量 API 消耗：配置 backend/.env 中的 MODEL_BASE_URL、MODEL_API_KEY、MODEL_NAME 后，在 backend 终端运行 `.venv/Scripts/python.exe -m tests.live_smoke`。它使用与应用相同的配置，不输出或保存密钥和对话正文。
手动重试可能再次计费；本地超时不保证上游停止生成。

## 结构与规范

LangSmith 指标监控已接入后端，默认关闭，只记录调用链、耗时、错误状态和 token 用量，隐藏对话正文。首次开通与本机配置见 [LangSmith 接入说明](docs/langsmith.md)。

- desktop/src/main：窗口、安全 IPC 和本地 HTTP；preload：仅暴露 health/chat。
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
本次不提供安装包、签名、云端部署、自动更新、历史持久化、模型切换或知识库。
