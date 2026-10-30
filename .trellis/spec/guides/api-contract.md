# 最低 API 合同 v1

依据：../product/decisions.md。以下为待实现合同，不是已运行端点。
仅 Electron main 访问 `http://127.0.0.1:8000`，renderer 只调用 preload 白名单。
后端绑定 loopback；开发者配置同一 MELO_LOCAL_TOKEN，main 添加 Bearer token。
此本地 token 与模型 API Key 分离，不能返回 renderer。所有端点鉴权；不启用浏览器 CORS。

## GET /api/v1/health

200：`{"status":"ok","model_configured":false}`。
只检查进程和配置是否齐全，不调用付费模型，不宣称上游可用，不暴露路径或密钥。

## POST /api/v1/chat

Content-Type: application/json。请求示例：

```json
{"messages":[{"role":"user","content":"我叫小明"},{"role":"assistant","content":"你好，小明"},{"role":"user","content":"我叫什么？"}]}
```

- 顶层仅 messages；1–39 条，严格 user/assistant 交替，首尾 user，拒绝 system/tool 和未知字段。
- 每条 content 为非空白字符串；user 最多 8000、assistant 最多 16000 Unicode code points（与生成输出上限一致，可继续回传）；总 content 最多 64000 code points。
- HTTP 请求体最多 1 MiB（包含 chunked 请求）；Pydantic 同时验证消息结构。JS 不以 UTF-16 length 代替合同计数。
- 系统提示由后端固定，客户端内容不提升为系统权限。
- 每次用客户端传入的上下文开始独立 Agent run，不再叠加服务端历史。
- 不静默裁剪历史。达到轮次/大小上限后提示新建会话；新建会话清空内存，待请求结束后才允许操作。
- 200：`{"request_id":"UUID","message":{"role":"assistant","content":"你叫小明。"}}`。
- 仅返回最终回答文本，不返回工具调用、中间推理、状态文件或供应商原始响应。
- SDK 返回空文本/不支持的内容块视为 UPSTREAM_ERROR；非空文本上限 16000 code points，超限报错，不截断为成功。
- 后端 Agent 总时限 60 秒（含工具循环），递归上限 10，模型单次输出上限建议 2048 tokens；main 等待 65 秒。
- 后端单 worker，同一进程最多一个生成请求；超出返回 429，不无限排队。失败或超时必须释放并发槽。

## 错误与 IPC

所有 HTTP 错误使用相同结构，包含畸形 JSON、参数验证和未处理异常：

```json
{"request_id":"UUID","error":{"code":"MODEL_TIMEOUT","message":"模型响应超时，请重试。","retryable":true}}
```

| HTTP | code | retryable | 场景 |
| --- | --- | --- | --- |
| 401 | UNAUTHORIZED | false | 缺少/错误本地 token |
| 413 | REQUEST_TOO_LARGE | false | body 超限 |
| 422 | INVALID_REQUEST | false | 结构/角色/内容/上下文长度不合法 |
| 429 | RATE_LIMITED | true | 本地并发或上游限流，提供 Retry-After（秒） |
| 503 | MODEL_NOT_CONFIGURED | false | 缺模型配置 |
| 502 | MODEL_AUTH_ERROR | false | 上游认证/权限失败，提示本机修改配置 |
| 502 | UPSTREAM_ERROR | true | 上游断网、服务失败或输出不合法 |
| 504 | MODEL_TIMEOUT | true | 生成超时 |
| 500 | INTERNAL_ERROR | false | 未知内部异常 |

后端生成 request_id 并在响应头 X-Request-ID 返回；不把上游异常文本直接给用户。
main 将连接失败映射为 BACKEND_UNAVAILABLE，将 IPC 等待超时映射为 BACKEND_TIMEOUT；均为 retryable=true，并生成 request_id。
IPC 返回可序列化联合类型 `{ok:true,data:...}` 或 `{ok:false,request_id,error:{code,message,retryable}}`，不依赖跨 IPC 抛异常保留字段。
preload 仅暴露 health()、chat(messages)，main 验证 sender、负载和响应结构，URL/路径由 main 固定，不接受 renderer 指定 URL。
不自动重试模型请求；用户手动重试可能再次计费，request_id 只作诊断，不承诺幂等。
