<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

# Melo 项目约定

先读 `.trellis/spec/product/decisions.md`，再读所触及层的 index 和 guides/api-contract.md、guides/testing.md。
应用已实现，验证状态见 README 与 docs/verification.md；后续改动必须运行所触及层检查。
用户已授权本轮配置 Trellis、编写规范和创建初始任务；无需重复询问是否可创建这项任务。
用户已接受默认值并授权实现初始任务。仅开发运行，不制作安装包。
规范可用中文；区分用户确认与建议默认值，不捏造已有源码模式。
本项目使用 inline 模式；不依赖 hooks 自动注入，后续会话主动读取规范。
