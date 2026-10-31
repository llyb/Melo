# 目录与 Agent 边界

建议 backend/pyproject.toml、uv.lock；app/main.py 配置 FastAPI/lifespan/异常处理，app/routes/chat.py 放 health/chat 路由，app/schemas.py 放 Pydantic DTO，app/agent.py 封装 Deep Agents，app/settings.py 读取环境变量，tests/ 放测试。
app/main.py 暂时直接包含两个路由，不单独拆 routes/chat.py；其余路径已实现。只做 route → agent 两层，不增加 repository 或通用 provider 插件层。
从后端 env 的 base URL、API Key、模型 ID 显式构造 OpenAI Chat Completions 兼容模型对象，再传给 create_deep_agent，不限定服务商；显式选择对应协议，不能误走 Responses API。GLM-5.3 使用 enabled thinking + low reasoning，其他模型不发送 GLM 专用字段。
必须用 Deep Agents 实际运行，不能用直接 SDK 调用假装接入框架。async 路由调用 ainvoke，不能阻塞事件循环。
仅 StateBackend 临时虚拟文件，不连接 FilesystemBackend、shell、MCP、网络业务工具；每轮无持久 checkpoint，禁止共享可变会话状态。
注意 tools=[] 只是“不额外添加”，不会移除内置工具。锁定版本后按官方支持方式禁用子代理/不需要的工具，并测试工具集合和无主机 IO；不能仅靠系统提示禁止副作用。
固定 system prompt；限制总超时、递归和模型输出，见 API 合同。未知结果不透传给前端。

当前锁定 Deep Agents 0.7.32；FilesystemMiddleware 必须保留 read_file，使用 tools=["read_file"] + profile excluded_tools 隐藏，StateBackend() 仅内存，关闭默认子代理。app/agent.py 和 tests/test_agent.py 已验证模型获得零个工具。
