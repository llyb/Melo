# 后端质量

Python 3.12 建议，FastAPI/Pydantic + Deep Agents，uv 锁依赖。ruff check 和 pytest 必须可离线运行；详细矩阵见 ../guides/testing.md。
配置缺失时 health 仍可探测，chat 明确返回 MODEL_NOT_CONFIGURED；不要把假响应作为正常运行模式静默启用。
模型替身仅在测试中显式注入。测试至少穿过真实 Agent 构造/运行和 DTO 边界，另测上游错误映射。
仅 loopback + 本地 token，单 worker；请求大小、角色、长度、并发和时限必须在后端校验。
