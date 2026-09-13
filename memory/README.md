# 本地记忆目录

程序的学习记录保存在这里，跨进程和会话持久化。SQLite、视频、模型、导出轨迹均默认 Git 忽略；此说明和 `project.md` 是可版本化的开发知识。

- `game-agent.sqlite3`：教程、运行和事件；还可能出现 `-wal`、`-shm` 文件。
- `models/action-memory.json`：`train` 输出的动作经验基线。
- `datasets/*.jsonl`：用户导出的已验证状态/动作轨迹。
- `videos/objects/*/raw/`：原始教程媒体；`videos/catalog.sqlite3` 保存独立的分类信息。
- `videos/reports/`：候选语义 JSON/Markdown；`videos/cache/`：文件哈希与语音缓存。
- `models/Qwen3-VL-2B-Instruct/`、`models/faster-whisper-small/`：第一阶段本地模型。
- `validation/video-stage1/`：合成输入与验证报告，不作为真实游戏学习记录。
- `STOP`：存在时阻止运行继续发送动作；程序不会自动删除。
- `project.md`：项目决策、已验证能力和已知限制。

查看记忆：`python -m game_agent recall`。备份数据库请使用 SQLite backup API，或者关闭程序后复制。日志和模型文件不包含 API token；新插件的密钥从环境读取，不写入教程或记忆。
