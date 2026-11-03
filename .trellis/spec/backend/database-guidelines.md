> 2026-11-03用户修订：仅保留一个Agent图及会话/run入口，删除旧/chat、reply和旧DTO。暂不设置Agent全轮时限、模型请求超时或图步数上限（原生循环使用infinity禁用默认有限上限）。spent仅为指标，不参与恢复准入；5会话并发、同会话一轮未决、MCP网络超时和修改审批有效期保留。下文旧兼容/60或120秒/10或25步规则为历史，已被本条覆盖。测试覆盖单次构图、31模型调用/30工具循环、超高spent恢复与旧路由404。

> 2026-11-02 catalog v2 新增临时 run_inputs、200项run_events与mutation_receipts；接受元数据/输入/首事件同事务，输入checkpoint引用保存后清除outbox。rename/head/publish字段在短BEGIN IMMEDIATE事务读改写，禁止旧快照回写覆盖新标题/版本。最后核对回执与解除needs_reconciliation同事务；v1升级保留历史，备份/回退复制完整停止后的data目录。
> 有外部副作用时不从base全轮重跑。MCP写前落executing，成功后succeeded；应答或回执提交不确定则先核对。相同tool_call_id/参数hash回放成功回执不再写。启动先捕获最新原生checkpoint，再分流未知回执；等待审批保留，其他中断需手动恢复。无外部回执且未审批的终态无效回答允许从base新attempt；checkpoint有效终态仅重发目录发布，不重调模型。删除会话不删除或回滚Obsidian笔记。

# 存储边界

2026-11-02用户批准多会话及会话内虚拟文件持久化，覆盖初始仅内存约定。使用官方AsyncSqliteSaver + StateBackend，每会话独立thread_id；应用catalog只保存目录、请求状态和checkpoint引用，不另存聊天或文件正文。

路径为当前用户LOCALAPPDATA/Melo/data；测试必须注入临时data_dir并运行lifespan。saver内部表不直接读写；目录短事务在线程执行，模型等待不持事务。成功head发布和请求记录同一目录事务；崩溃后先检查原生checkpoint终态，不擅自重跑付费模型。

失败分支可落盘但不成为成功head；从base重试不继承失败文件。删除先tombstone，再adelete_thread，最后清理目录；启动继续未完成删除。不删全库实现单会话删除或代码回滚。未知catalog版本拒绝启动，saver schema由官方setup维护。

数据未加密，备份先停止后端并复制整个目录。跨会话记忆、实体文件导出暂未实现；StoreBackend/FilesystemBackend为可选技术，不是用户禁止项。
