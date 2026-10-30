# 产品与技术决策（2026-10-30）

这是空项目的开发基线，规则来自本次需求和下列公开文档，不是假称已有源码实践。
用户于本次后续指示接受全部建议默认值，并明确授权开始实现。

## 用户已确认

| 决策 | 内容 |
| --- | --- |
| 目标 | 先搭基本框架，一个 Agent 页面实现基本对话 |
| 前端 | Vue + Electron |
| Agent 框架 | Deep Agents |
| 交付 | 先开发运行，暂不制作安装包 |
| 模型服务 | Z.AI 标准 API，用户指定 https://api.z.ai/api/paas/v4 |

## 已接受的默认值

| 问题 | 建议 | 不同选择的影响 |
| --- | --- | --- |
| 首个运行平台、用户范围 | Windows 本地单用户开发 | 多用户/远程需重新设计身份、隔离和部署 |
| 后端语言/服务 | Python 3.12+、FastAPI、Uvicorn，单进程 | 不引入另一套 JS Agent 后端 |
| 前端构建 | Vue 3、TypeScript strict、electron-vite、npm | 先不用 UI 库、Router、Pinia |
| 交互与输出 | 中文界面，纯文本，非流式 HTTP；等待中禁用发送 | 流式需另定事件、取消与断线语义 |
| 上下文 | 一窗口一会话；前端内存保留全部成功轮次，每次显式提交 | 不使用数据库或 checkpointer；刷新/重启丢失 |
| 模型配置 | 后端环境变量；单一 GLM 模型，无切换 UI | 后续设置页需补密钥存储方案 |
| 后端启动 | 开发者单独启动 Python；Electron 探活并报错 | 首次不做 Python 打包或自动进程管理 |
| 能力边界 | 文本对话，不接 MCP、Obsidian、真实文件系统、shell 或外部工具 | 记忆和知识库属于后续独立任务 |

## 模型接入修正

- 用户指定标准 API `https://api.z.ai/api/paas/v4`，使用 OpenAI Chat Completions 兼容协议；不再使用 Coding Plan 端点。
- 默认模型 `glm-5.3` 取自 Z.AI 官方快速开始，作为实施方选择，可通过 MODEL_NAME 修改；本轮已用临时进程凭据完成 glm-5.3 两轮真实 Deep Agents 校验。
- Key 仅后端本机环境变量 MODEL_API_KEY。用户曾在聊天粘贴 Key，不复制到任何仓库文件或日志；建议更换后再联调。
- 真实联调需可用的本机凭据，离线测试不需要凭据。
- 本机现有 Python 3.13；实现兼容 Python 3.12+，测试后记录实际版本。

## 版本策略

实现时验证 Python 3.12 与依赖的兼容性，选择受支持 Node LTS 和 Electron，记录准确运行时版本。
提交 package-lock.json 和 uv.lock；CI 使用 npm ci、uv sync --frozen。本文不凭空指定未安装验证的库版本。
Trellis CLI 现有版本为 0.6.17；本次不升级全局工具。

## 依据

- [Trellis](https://github.com/mindfold-ai/Trellis)：项目规范、任务和工作日志结构。
- [Deep Agents quickstart](https://docs.langchain.com/oss/python/deepagents/quickstart)：模型需要支持 tool calling。
- [Deep Agents API](https://reference.langchain.com/python/deepagents/graph/create_deep_agent)：显式模型、默认工具和 backend/checkpointer 边界。
- [Electron security](https://www.electronjs.org/docs/latest/tutorial/security)：进程隔离与 IPC 验证。
- [智谱快速开始](https://docs.bigmodel.cn/cn/coding-plan/quick-start)、[指定环境](https://docs.bigmodel.cn/cn/coding-plan/tool/others)：权限、Key 和协议须分别核对。

- [Z.AI 标准 API 快速开始](https://docs.z.ai/guides/overview/quick-start)：用户端点及默认模型依据。
