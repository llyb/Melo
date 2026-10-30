# 日志

使用 Python 标准 logging，字段至少 timestamp、level、request_id、route、status、duration_ms 和安全 error_code。
INFO 记录调用结果，WARNING 记录可恢复上游错误，ERROR 记录内部故障；不能直接记录供应商异常 repr 或含输入的堆栈局部变量。
禁止记录 Authorization、模型 Key、完整环境变量、请求/响应正文和工具内容。不要开启 SDK 请求体调试或外部 tracing。
日志只用于开发诊断，不引入遥测平台；后续需要远程追踪先确定内容脱敏和用户授权。
