# 日志

使用 Python 标准 logging，字段至少 timestamp、level、request_id、route、status、duration_ms 和安全 error_code。
INFO 记录调用结果，WARNING 记录可恢复上游错误，ERROR 记录内部故障；不能直接记录供应商异常 repr 或含输入的堆栈局部变量。
禁止记录 Authorization、模型 Key、完整环境变量、请求/响应正文和工具内容。不要开启 SDK 请求体调试。
用户已授权 LangSmith 指标监控；仅在显式开启并配置 Key 后上传，默认关闭。所有层隐藏输入/输出，异常只留通用失败标记，metadata 白名单保留请求 ID、模型与数字用量。
监控上传失败不影响对话；API request_id 对应根 trace ID。实现见 backend/app/agent.py，验证见 backend/tests/test_monitoring.py；[接入说明](../../../docs/langsmith.md)。
