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
