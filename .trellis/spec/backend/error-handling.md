# 错误处理

所有状态、错误码、retryable 字段以 ../guides/api-contract.md 为准，禁止另建一套 envelope。
集中处理 HTTPException、RequestValidationError、畸形 JSON、超大 body 和未捕获异常；422 不返回包含原始输入的默认 Pydantic 明细。
路由边界映射供应商认证/限流/连接/超时异常；未知异常返回安全 INTERNAL_ERROR，内部按 request_id 记录已脱敏诊断。
不吞异常、不返回 HTTP 200 假成功、不自动重试付费调用。使用 finally 释放生成槽；超时取消本地任务，说明不能保证上游停止计费。
