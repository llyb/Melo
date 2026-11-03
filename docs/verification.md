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

## LangSmith 监控验收 · 2026-10-30

- 后端 34 项测试与 Ruff 通过（接入阶段），覆盖显式开关、隐藏正文、用量、请求关联、批量传输、上传失败和关闭清理。
- 用户完成本机凭据配置后，真实 FastAPI + Deep Agents + glm-5.3 请求成功；云端 melo/local 回读到完整的 12 个节点和 1 次模型调用，输入 39 / 输出 8 / 合计 47 tokens。
- 全部节点成功且已结束，输入输出为空；实际回读数据未包含本机模型 Key、LangSmith Key 或本地令牌。凭据仍只在被 Git 忽略的本机配置中。
- 本轮未重新验证桌面界面；现有 8000 端口服务未停止。未提交或推送这些监控改动。

## 自定义模型接口 · 2026-10-31

- 按用户修订取消 Z.AI 地址限制，读取后端 env 的 MODEL_BASE_URL、MODEL_API_KEY、MODEL_NAME；普通兼容模型不发送 GLM 专用参数，GLM-5.3 使用 enabled thinking + low reasoning。
- 47 项后端测试及 Ruff 通过，包含自定义 HTTP(S) 地址、无效 URL 脱敏拒绝、实际 ChatOpenAI 请求参数和最终回答提取。
- 使用本机临时 HTTP 模拟服务执行实际 tests.live_smoke，验证自定义地址、Key、模型名及两轮 Deep Agents 调用，未访问付费模型。这不能替代新服务的真实联调。
- 排错时原 Z.AI 服务先返回 400/1210（不支持关闭思考）；修正参数后返回 429/1113（余额不足或没有资源包）。当前凭据仍不能完成真实聊天。未替换用户本机配置、重启既有服务、提交或推送；修改 env/代码后需重启后端。

## 2026-11-02 多会话及会话内虚拟文件

- 官方langgraph-checkpoint-sqlite 3.1.3、aiosqlite 0.22.1；现有Deep Agents 0.7.32 / LangGraph 1.2.18保持。
- 后端ruff通过，pytest完整62项回归通过；覆盖真实文件工具、连接重开隔离、失败分支、摘要后的历史引用、catalog发布失败恢复、文本块输出、严格DTO、并发/超时、监控关联和删除。
- 前端lint/typecheck通过，Vitest 8项通过，electron-vite build通过。
- npm run test:desktop通过：真实Electron preload/IPC和离线Deep Agents，两轮上下文、新会话、窗口刷新历史读取、后端停止/恢复与输入保留重试、已保存会话读取/删除。采用独立端口和临时数据目录，不影响8000开发服务。截图可能不可用，不跳过功能断言。
- 独立只读审阅发现3项缺陷，均已修复并添加回归测试。未验证本次真实付费模型调用、签名/安装包、云端部署；已补充fresh Electron和fresh backend进程的独立恢复阶段，通过真实preload/IPC读取持久会话。
- 数据目录与明文/草稿/失败checkpoint边界见README；跨会话记忆和实体文件后端本轮不启用。
## 2026-11-02 Obsidian 原生 MCP 与后台会话

- 实现：最多5会话并发、每会话一轮未决、发送立即清输入、保留独立草稿、导航/左栏原位改名与 √ 保存；真实活动、审批和未知写核对通过具名IPC投影。
- 依赖：保持 Deep Agents 0.7.32 / LangChain 1.4.7 / LangGraph 1.2.18，新增锁定 langchain[mcp] extra；使用 MCPAdapter、FastMCP 4.1.5 / MCP 2.3.0 原生 Streamable HTTP，没有自制MCP协议。
- 后端：Ruff、完整 pytest 84项通过。覆盖5并发与legacy共享容量、输入outbox/首checkpoint前恢复、原子标题/发布、原生多动作审批/拒绝/重启/过期、写应答丢失去重、回执落盘失败未知优先、核对与结束竞态及事务回滚、旧revision恢复、终态无效回答重试；新执行路径用真实LangSmith SDK离线传输验证不上传正文/密钥。
- 前端：ESLint、TypeScript、Vitest 13项通过；electron-vite build通过；实际 Electron preload/IPC 两轮上下文、提交立即清空/输入和新建保持可用、断开后端/重启/同turn重试、刷新和全新前后端进程恢复均通过。真实桌面检查发现并修复响应式Proxy不可跨IPC克隆的问题。
- 本机 MCP：使用用户授权配置完成认证、list_tools和条件写schema核验；仅新建并读取一篇专用 `Melo Integration Tests/mcp-*.md` 笔记。随后通过实际原生MCP + Deep Agents（确定性模型）读取该笔记、生成更新提案、暂停审批、拒绝后完成，确认版本/内容均不变。没有读取无关笔记，没有实际批准修改已有笔记。
- 本机凭据只存Git忽略的backend/.env，插件CA只存忽略的.local目录；TLS验证启用，未更改系统信任。catalog v2保留v1数据；回退/明文及外部笔记不可回滚边界见README。
- 独立只读复核提出的持久化原子性、迟到响应、未知写优先和终态重试问题已修复；最终复核无阻断项。未推送、合并或重启用户8000开发服务。

未检查：本轮付费模型、真实已有笔记批准写入、Python 3.12、新机器/安装包/远程CI；Electron capturePage在本桌面不可用，视觉截图未验收（功能DOM与实际IPC已检查）。原生MCPAdapter目前为beta，升级依赖前应复测本机插件协议。

## 2026-11-03 单Agent与移除执行预算

- 按用户要求在feat/obsidian-background-runs修改。只构造一个Deep Agents图、一个execute_run执行入口；删除旧/chat、reply/_reply、legacy_graph及旧DTO，原run_turn测试便利函数移到tests，不在生产中保留兼容入口。
- 删除全轮120秒预算、恢复预算拒绝与有限递归上限；模型请求timeout=None。使用当前锁定LangGraph原生循环的infinity步数配置，不退回默认有限上限。spent仅作指标。5会话并发、会话隔离、修改审批及MCP网络超时仍保留。
- Ruff及完整66项pytest通过；覆盖单次构图、30次工具循环/31次模型调用、百万秒spent恢复、旧/chat404、持久化/审批/监控。原旧接口专用测试删除或迁到统一持久入口，模型协议测试按真实事件流迁移。
- electron-vite build与真实Electron两轮对话、断线后重试、fresh前后端进程恢复通过；独立端口和临时DB，未停止8000开发服务。
- 未执行付费模型或长时间真实运行、未重测真实Obsidian；截图仍不可用。关闭模型超时后，卡住的请求可能长期占用并发槽；用户可停止后端再显式恢复。已有数据不迁移、不清除。

- 2026-11-03追加计时修复：仅accepted/running启动活动区时钟；终态或暂停清理计时器并隐藏相对时间。完成/失败/结束三个组件回归先失败后通过；完整前端16项Vitest、lint/typecheck/build通过。未单独重跑Electron和后端，本次只改页面计时。
