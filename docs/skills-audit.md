# GPT-6 项目技能适配记录

检查日期：2026-09-13。范围为本次任务相关的三项已安装技能和本项目目录，不宣称审计了全部全局技能。

| 技能 | 实际检查结果 | 本项目处理 |
|---|---|---|
| `/home/wanglc/.agents/skills/codebase-memory/SKILL.md` | 基于工具与证据层级，无固定旧模型要求 | 保留图优先检索和覆盖检查流程 |
| `/home/wanglc/.codex/skills/.system/skill-creator/SKILL.md` | 强调任务范围、渐进披露和用户优先，支持指定位置 | 用于编写本地技能 |
| `/home/wanglc/.agents/skills/create-skill/SKILL.md` | 指向 `.cursor/skills`；默认 `disable-model-invocation: true` | 不照搬其路径与调用默认值；全局文件不修改 |

问题是路径、工具和行为约定不一致，不是 Markdown 技能天生只支持某代模型。GPT-6 对技能和 AGENTS 指令更敏感，因此新技能只写本项目需要的接口约束、验证方法和记忆约定，避免冲突指令、无关流程及无条件暂停。[OpenAI GPT-6 指南](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)

新技能：`.agents/skills/game-agent-gpt6/SKILL.md`。范围仅为当前项目，保留正常自动发现，也可用 `$game-agent-gpt6` 显式调用；根目录 AGENTS.md 提供固定入口。技能沿用 name/description + Markdown 的格式。[技能编写文档](https://learn.chatgpt.com/docs/build-skills)

没有修改全局技能、全局模型配置或 shell 配置。技能文件不选择或安装 GPT-6，不训练 GPT-6 权重；实际运行模型由当前 Codex 会话决定。“适配 GPT-6”表示审阅并优化指导其开发这个项目的指令。

验证包括官方 skill-creator 的 quick_validate，以及对技能引用的目录、命令和框架行为的检查。新技能的 UI 自动发现取决于宿主刷新；如果当前会话尚未列出它，可以让 Codex 读取上述具体路径。
