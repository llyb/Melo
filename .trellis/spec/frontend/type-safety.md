# 类型与信任边界

启用 TypeScript strict。消息 role 为 user | assistant，失败结构与 API 合同保持一致。
shared/chat.ts 定义 IPC 数据类型；Pydantic/OpenAPI 是 HTTP 合同来源，变更时同步类型与合同测试。
声明 Window.melo 类型；禁止 any 和用类型断言代替运行时验证。
main 验证 renderer 入参和 HTTP 响应；renderer 对 IPC 失败做兜底展示。具体字段和限额见 ../guides/api-contract.md。
