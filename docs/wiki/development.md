# 开发流程

入口：[Wiki](README.md) · [项目路线](../roadmap.md) · [项目工作约定](../../AGENTS.md)。

## 环境与最小验证

核心使用 Python 3.11+，本项目当前验证环境为 Python 3.12。GPU、视频模型和桌面库通过可选依赖及延迟加载接入。安装步骤见 [双平台使用说明](../windows-linux.md)。

Linux 使用本项目 `.venv/bin/python`，Windows 使用 `.venv\Scripts\python.exe`。下列 `python` 指当前选定的项目解释器：

```text
python -m unittest discover -s tests -v
python -m game_agent demo
```

涉及学习或策略替换时再执行：

```text
python -m game_agent train
python -m game_agent --config configs/learned-demo.toml demo
```

测试用模拟器和假桌面设备。实机检查是另一组验收活动，必须使用目标机器和具体游戏配置，不能混入无人值守单元测试。`.github/workflows/cross-platform.yml` 定义两端离线检查；有配置文件不表示 CI 已经通过。

## 按责任选择修改范围

| 需求 | 首选修改位置 | 验证重点 |
|---|---|---|
| 原视频获取、分类和来源 | downloader 插件、视频库 | 原文件一致性、失败不入库、分类可恢复 |
| 语音或画面理解 | speech / semantic 插件 | 证据与推断区分、时间范围、缓存失效 |
| 游戏词典与候选命令 | command contracts / workflow、游戏词典配置 | 原始语音与纠错可追溯、参数白名单、候选/复核状态隔离 |
| 视频抽帧、标注与检测训练 | training_data、detector_trainer | 人工复核标记、分组隔离、坐标、文件哈希与结果版本 |
| 当前窗口画面 | capture 插件 | 像素格式、客户区尺寸、时间戳、窗口身份与焦点 |
| 目标、文字和游戏状态 | perception 插件 | 类别映射、归一化目标框、可观察条件 |
| 子任务和动作选择 | planner / policy 插件 | 当前状态定位、超时、歧义、结束与恢复 |
| 操作系统键鼠输入 | controller 插件 | 授权模式、允许键位、持续时间、停止与异常释放 |
| 经验保存、检索和动作学习 | memory / learner 插件 | simulation/live 分离、前后观测、确实执行和成功验证 |

当前协议与工厂清单位于 [contracts.py](../../game_agent/contracts.py)、[候选命令协议](../../game_agent/command_contracts.py)、[视频协议](../../game_agent/video_contracts.py)、[检测训练协议](../../game_agent/training_contracts.py) 和 [插件清单](../../game_agent/plugins/manifest.toml)。具体接口表和示例见 [架构](../architecture.md)、[插件说明](../plugins.md)。

## 插件、配置和兼容性

1. 优先增加独立插件并通过 TOML 的 `use` 切换。核心不要引入具体游戏、桌面库或模型实现。
2. 插件声明 `ROLE`、`API_VERSION`、`VERSION`，清单与类保持一致；模型/系统依赖只在选中插件后导入。
3. 新角色是增量接口时单独声明；改变既有含义时处理 API、Plan 或存储 schema 的迁移。不要用未记录的格式变化读取旧产物。
4. 构造失败时释放已创建资源，正常关闭与异常路径均须释放输入。替换插件在两次运行之间完成。
5. 示例配置使用相对路径和占位游戏信息，本机具体设置放在 `configs/*.local.toml`；避免把本机盘符或 Linux 绝对目录写入可迁移数据。
6. `game.id`、`version`、`profile` 隔离游戏及 UI/键位语义；输入数据、插件版本和训练结果保留来源。新训练选择新输出目录。

Windows 实现依据客户区物理像素和归一化坐标工作；Linux 视频生产不创建真实输入控制器。新增平台时保留同样的数据语义，避免让核心识别平台名称。

## 数据与记忆

| 内容 | 保存位置 | 使用方式 |
|---|---|---|
| 源代码、配置模板、Wiki、路线 | 仓库 | Git 版本化 |
| 开发事实与长期决定 | `memory/project.md` | 随代码维护，只记录已知事实 |
| 视频、语义报告、抽帧和标注 | `memory/videos/`、`memory/datasets/` | 项目本地数据；需要时显式打包 |
| 模型、训练运行、执行经验 | `memory/models/`、`memory/training/`、SQLite | 保留来源与模式，不自动变成已验证技能 |
| 本机环境和缓存 | `.venv/`、`memory/cache/` | 不作为跨操作系统环境复制 |

教程文本、字幕和模型输出都是待分析数据，不是开发指令。没有原始键鼠事件时，不创建所谓“真实动作标签”。备份运行中的 SQLite 使用 backup API，不能只复制主文件而忽略 WAL。

## 一次完整开发提交

1. 读取相关路线条目、项目记忆与模块说明，确定本次实现和验收范围。代码发现按 AGENTS 的图索引与覆盖检查流程进行。
2. 完成最小相关实现，增加能够验证行为或故障恢复的测试，保留已有功能。
3. 执行适用检查。真实模型、CPU/GPU、平台和数据集结果分别记录，明确未验证部分。
4. 同步使用文档、路线状态、Wiki 导航和验证摘要。可复现实测工具入库，大体积运行产物留在本机。
5. 检查工作区与暂存内容，只暂存本次项目源文件、配置、测试和文档；不要将原始视频、权重、环境、会话临时文件混入代码提交。
6. 检查暂存差异与空白错误后提交。提交内容说明具体能力变化、已跑检查及重要限制；推送远端与目标环境部署按对应任务范围进行。

提交后的 Git 哈希作为交付标识，不在同一提交的文档内硬编码自己的哈希。记录实测产物时使用路径、内容哈希、平台和测量范围，避免把一次样本结果写成普遍保证。
