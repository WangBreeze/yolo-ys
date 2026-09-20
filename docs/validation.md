# 验证记录

更新日期：2026-09-20。入口：[项目路线](roadmap.md) · [开发 Wiki](wiki/README.md)。

当前环境为 Linux、Conda `yolo26` / Python 3.12.14，项目 `.venv` 复用该环境的 PyTorch。以下分别记录代码回归、真实媒体、合成训练和迁移结果。Windows 原生运行与真实游戏输入尚未验收。

## 当前回归结果

| 验证 | 结果与范围 |
|---|---|
| `python -m unittest discover -s tests -v` | 75 项通过；覆盖插件替换、命令 schema/词典/提取、记忆隔离、视频库与语义缓存、Windows 路径/缓存兼容和假设备、标注/数据集隔离及迁移打包 |
| `python -m game_agent demo` | 模拟商店任务成功，观察到购买和装备条件 |
| 原神候选命令 | P1–P20 共生成 674 条，54 条保留语音纠错记录；20 个文件均通过 schema 与词典校验；尚未人工复核或编译为 Plan |
| `python -m game_agent train` | 从已验证的模拟轨迹生成动作经验表；不代表神经网络训练或实机能力 |
| `python -m game_agent --config configs/learned-demo.toml demo` | 替换为动作经验策略后完成同一模拟任务 |
| Windows 插件测试 | 在 Linux 使用假窗口/输入设备检查结构体布局、负坐标、焦点与窗口变化、画面时效、停止及异常释放；不发送真实输入 |
| 数据集检查 | 未复核帧会被拒绝；检查录制组/视频/图片跨集合泄漏、路径、坐标和内容哈希 |
| 跨平台 CI | 已提供 Ubuntu/Windows 工作流；没有已验证的远端运行结果，本地提交不等于 CI 已执行 |
| 本次第二阶段改动 | `list-commands`、P10 提取/校验、20 集批量提取/逐文件校验和差异空白检查通过 |

回归使用项目解释器；复现命令见 [开发流程](wiki/development.md)。基础框架不需要下载模型或创建真实输入后端。

## 视频理解与检测

| 素材与配置 | 实际结果 | 限制/本机证据 |
|---|---|---|
| `people_2k.jpg`、已有 YOLO26s、GPU `cuda:0`、输入 640 | 插件返回 13 个 person/umbrella 目标；阻断 Python `socket.connect` 后运行成功 | 功能检查，不是识别准确率或 Windows 30ms 验收 |
| 合成 12 秒商店教程，Qwen3-VL-2B + faster-whisper small | 首次完整语义约 8.10 秒，模型复用重算约 4.57 秒，缓存约 30.8ms | 不含进程启动；存在小字误读和点击推断，详见本机 `memory/validation/video-stage1/result.json` |
| 用户教程 `BV1dt42147zq`，28.03 秒、852×480、fast 12 帧 | 首次本地分析 12.58 秒，未命中缓存；另行复核关键画面 | 不含进程启动与 Codex 画面复核；本机 `memory/videos/analysis/6235bf107aea1d29804a/reviewed.md` |

所需视觉/语音权重已在本机安装并推理验证，推理使用本地权重和 Hub 离线设置。下载视频、依赖与初始权重需要网络；Python 连接守卫的结果不是操作系统级网络审计。

真实教程显示在背包任务页使用餐品后出现成就提示，片尾没有展示委托最终完成。小模型初稿出现位置误判和过度推断，原始输出保留，复核说明单独保存。一个教程样本不能作为普遍准确率结论，也没有据此形成实机成功经验。

## 离线视觉训练与迁移

两个不同的合成录像分别提供 4 张训练图和 4 张验证图。已有 YOLO26n 权重在 CPU 上真实训练一轮，`imgsz=64`、batch 2、workers 0，产出 `weights/best.pt` 和带来源哈希的训练记录。训练函数耗时 **2.49 秒**，不含检查脚本中更早的数据准备/导入；precision、recall、mAP 均为零，只用于验证链路可运行。证据为本机 `memory/validation/offline-training/result.json`。复现工具为 [check-offline-training.py](../tools/check-offline-training.py)，每次应选择新的输出目录。

原神教程已准备 32 个 PNG 和 `annotations.json`，位于本机 `memory/datasets/genshin-food-v1/`，全部 `reviewed=false`、`split=unassigned`。实际执行数据集构建已确认拒绝这些未复核数据；尚无独立验证录像、正式游戏检测模型、同步人工键鼠数据或行为克隆模型。

历史迁移包 `memory/transfers/project-windows.zip` 的 116 个文件、两条原始媒体流、32 个标注帧哈希均已核对。在 Linux 下解压到含空格和中文的不同目录，禁用项目环境/site-packages 后，doctor、demo、train、learned-demo 通过。该结果证明当时快照可迁移到另一目录，**不等于 Windows 原生验收**；此历史包不包含随后新增的路线图与 Wiki。证据为本机 `memory/validation/windows-portability.json`；重新打包步骤见 [双平台说明](windows-linux.md)。

## 历史基线与待验证项

初版框架为 28 项测试通过，视频阶段扩充至 43 项，双平台与视觉训练阶段为 68 项，候选命令阶段为 73 项，Windows CI 兼容修复后为 75 项。初版离线 wheel 构建、项目技能检查、demo → train → learned-demo → recall → export 均通过；历史记录保留于 [项目记忆](../memory/project.md)。

仍待验证：Windows 实际窗口/DPI/截图/输入兼容性、真实游戏任务与恢复、独立录制数据集的检测质量、2K 实机延迟目标。Linux uinput/截图联动也尚未实机验收。单元测试、合成素材或迁移检查均不能替代这些结果。

`memory/` 的视频、模型、数据库和详细运行产物不进入 Git；全新克隆可查看本页摘要并用工具复现，详细本机证据需要单独迁移。
