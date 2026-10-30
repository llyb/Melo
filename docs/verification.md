# 验证记录 · 2026-10-30

- 后端：22 项 pytest 通过，ruff check 通过。
- 前端：7 项 Vitest 通过，ESLint、TypeScript、Electron/Vue build 通过。
- 实际桌面：Electron 42.11.18 启动，通过 Vue → preload → IPC → FastAPI → Deep Agents 替身模型完成两轮上下文，清空、断开后端后保留输入、恢复后重试成功。
- 真实上游：Z.AI 标准端点，glm-5.3，通过实际 Deep Agents 进行两轮校验码记忆检查；两次调用成功。凭据只存在临时进程环境，没有保存到项目文件或输出。
- 独立审阅：长回复回传上限与环境继承追踪两项缺陷已回归修复；其余无重要发现。
- 密钥检查：源码和项目文档不含用户提供的 Key；两个本机 .env 仅初始化本地令牌与空的模型 Key，Git 忽略。

限制：当前桌面 capturePage 返回 UnknownVizError，未完成截图与视觉布局检查；功能 DOM 和实际 IPC 检查均执行并通过。
尚未测试 Python 3.12（本机为 3.13.13）、全局 Trellis hooks、全新机器安装或 CI；首版不制作安装包。

实现选择：因 Deep Agents 0.7.32 要求保留 read_file，保留仅内存的 StateBackend 并通过 profile 隐藏此工具，关闭默认子代理；实际模型获配工具列表为空。没有主机 IO backend。
