# 最低测试与开发验收

依据：API 合同和已实现的 Agent 页面。以下为现有检查接口。

| 层 | 工具 | 必须覆盖 |
| --- | --- | --- |
| Vue | Vitest + Vue Test Utils | 空白禁发、发送/成功、等待禁重发、失败保留输入、重试无重复消息、新会话清空、多轮上下文 |
| IPC/main | Vitest | sender 白名单、固定路径、无本地 token/模型 Key 泄露、负载/响应验证、后端离线和超时映射 |
| Python/API | pytest + httpx | health 无付费调用、401、413、422、成功响应、无配置、上游认证/限流/异常/空输出/超时及错误 envelope |
| Agent | pytest + 可控模型替身 | 实际 create_deep_agent 调用链、最终回答提取、上下文不重复/不串话、无主机 IO 工具、总时限与循环上限 |
| 并发 | pytest | 并发第 2 个请求 429，失败/超时后槽释放 |
| 桌面冒烟 | 人工记录 | Windows 启动 Electron，发两轮，断开后端出现可重试错误，恢复后成功，新会话清空 |

默认测试不需要真实 Key、不访问公网，固定替身输出；禁止断言某段随机模型原文。
真实模型冒烟由开发者显式执行，使用后端 env 的 base URL、API Key 和模型 ID，配置可用权限后验证一次两轮对话和协议兼容性，记录日期、模型 ID、锁文件版本和结果，不记正文/Key。离线测试覆盖非 Z.AI 地址、HTTP(S) 和 URL 校验，并用实际 SDK 请求验证普通模型不含 GLM 专用字段、GLM-5.3 参数兼容及只返回最终回答。
仅有 mock 不能宣称真实模型已接通；仅有浏览器组件测试不能宣称 Electron IPC 可用。

## 实现任务应提供的检查

```powershell
cd desktop
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
cd ../backend
uv sync --frozen
uv run ruff check .
uv run pytest
```

CI 采用 Windows runner（远程平台建议 GitHub Actions，待仓库确定），执行上述无 Key 检查；没有远程仓库时先保证同一组命令本地通过。
LangSmith 改动必须运行 tests/test_monitoring.py 及完整 pytest：用真实 SDK 的离线传输验证所有层隐藏正文/凭据/原始异常，保留数字 usage、父子调用关系与 request_id。必须覆盖关闭时不创建客户端、上传失败不影响聊天，以及异常退出时清理。
默认测试不得发送真实 traces。云端接通需要有权限的本机 Key 后单独验证，不得将离线通过描述为云端成功。
