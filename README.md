# 本地游戏模仿框架与 YOLO26 性能测试

本项目提供插件式游戏代理：理解本地教程、根据当前游戏状态操作、验证结果，并把教程与执行经验保存在本目录。保留原有 Ultralytics YOLO26 图片检测和 2K 性能测试。

[项目路线](docs/roadmap.md) · [开发 Wiki](docs/wiki/README.md) · [原神实时感知方案](docs/genshin-realtime-perception.md) · [YOLO 训练计划](docs/genshin-yolo-training-plan.md) · [开发流程](docs/wiki/development.md) · [验证记录](docs/validation.md)

## 文档与 Wiki 索引

完整导航以[项目开发 Wiki](docs/wiki/README.md)为入口：

| 内容 | 入口 |
|---|---|
| 项目阶段、下一步和开发约定 | [项目路线](docs/roadmap.md) · [开发流程](docs/wiki/development.md) |
| 核心结构、插件边界和本地学习 | [架构](docs/architecture.md) · [插件接入](docs/plugins.md) · [记忆与训练](docs/learning.md) |
| 视频下载理解与语音候选命令 | [第一阶段](docs/video-stage1.md) · [第二阶段](docs/voice-command-stage2.md) · [P10 复核表](docs/reviews/BV1P6SNYREo8/P10.md) |
| 原神实时状态识别与 YOLO 训练 | [实时感知方案](docs/genshin-realtime-perception.md) · [训练计划与进度](docs/genshin-yolo-training-plan.md) |
| Linux/Windows 使用与验证证据 | [双平台说明](docs/windows-linux.md) · [验证记录](docs/validation.md) |
| 当前版本化视觉基线 | [模型说明](models/README.md) · [训练报告](docs/reports/genshin-ui-yolo26n-v1-training.json) · [评估报告](docs/reports/genshin-ui-yolo26n-v1-evaluation.json) |
| 项目内 GPT-6 开发约定 | [技能适配检查](docs/skills-audit.md) · [项目技能](.agents/skills/game-agent-gpt6/SKILL.md) |

## Linux 训练与 Windows 运行

Linux 用于下载视频、读取语义、制作标注数据集和训练视觉模型；Windows 使用独立的窗口采集与 SendInput 插件运行游戏。Windows 默认配置使用 dry-run。当前在 Linux 完成离线验证，Windows 游戏实机尚未测试。

Windows 在项目目录先运行 `python tools/setup-project.py --profile windows`，随后用 `tools\game-agent.cmd demo` 检查环境。视频功能使用 `tools\youget.cmd`、`tools\video.cmd`；安装、窗口接入、Linux 标注训练和迁移方式见 [双平台使用说明](docs/windows-linux.md)。

已提供 `prepare-dataset`、`build-dataset`、`check-dataset`、`train-detector`，视觉训练与原来的动作经验 `train` 分开。当前已用33张短教程训练帧和19张P10/P13独立验证帧完成8类 YOLO26n 教程基线；5.12 MiB 的[基线权重](models/README.md)已随仓库保存。小地图和交互提示独立召回为0，背包界面存在误报，因此该权重只验证训练与迁移链路，尚不能用于真实游戏决策。

## 第一阶段：下载教程并理解内容

`you-get` 下载完成后默认归类为“视频教程”，保留原始流。理解是独立步骤，输出中文摘要、分段观察、可能的操作目的、不确定内容和实际耗时。

```bash
conda activate yolo26
bash tools/setup-video.sh
.venv/bin/python tools/fetch-video-models.py
./tools/youget '视频链接'
./tools/video videos
./tools/video understand 视频编号
```

工具、模型和语义记忆均留在本项目。默认使用 Qwen3-VL-2B、faster-whisper small；快速模式采样 12 帧，支持细化、批量复用模型和结果缓存。下载不做剪辑、拼接或转码。完整命令和速度取舍见 [视频下载与语义理解](docs/video-stage1.md)。

## 第二阶段：语音转候选游戏命令

第二阶段把带时间语音与画面语义整理成带证据的候选语义命令，经人工复核后编译为版本化 Plan。当前原神词典包含 28 个命令，动作分类和安全约束参考本机 BetterGI 固定提交；语音不会直接变成固定按键，也不会在 Linux 上操作游戏。

```bash
# 查看词典
python -m game_agent list-commands

# 从第一阶段报告生成候选命令，然后独立校验
python -m game_agent extract-commands memory/videos/reports/eef46c4fbf481c89cd0921f96bb69e4fed3fcb86b4838cd4680677b94cc56d82.json \
  --output memory/commands/BV1P6SNYREo8/P10.json
python -m game_agent check-commands memory/commands/BV1P6SNYREo8/P10.json
```

20 个分P的本地候选结果位于 `memory/commands/BV1P6SNYREo8/`，汇总入口为 `index.json`。开始实际执行前仍需人工复核、真实游戏 build/profile、键位、可观察状态、感知模型和 Windows dry-run 验证。完整环境、数据和验收条件见 [第二阶段说明](docs/voice-command-stage2.md)。

## 游戏框架快速开始

基础框架只需要 Python 3.11+，可直接在项目目录运行：

```bash
conda activate yolo26
python -m game_agent doctor
python -m game_agent demo
python -m game_agent recall 购买
python -m game_agent train
python -m game_agent --config configs/learned-demo.toml demo
```

这个流程实际执行“打开商店 → 购买 → 装备”的模拟任务、持久化经验，再替换为学习得到的动作策略。`memory/game-agent.sqlite3` 和 `memory/models/action-memory.json` 留在本机，默认不提交 Git。

当前交付是可运行的通用框架，demo 使用动作驱动的模拟游戏和人工标注教程。接入真实游戏需要本机窗口信息、游戏专用感知/键位配置和教程。Qwen3/Whisper 视频语义已在 Linux 实测；Hyprland/uinput、Windows/MSS/SendInput 已提供实现，桌面联动仍需实机验收。

原有八类插件分别负责教程、采集、感知、规划、策略、控制、记忆和训练；视频功能另增下载、语音、语义角色，离线视觉训练新增 detector_trainer。通过 TOML 清单和配置替换，核心不依赖具体模型。`train` 是动作经验表学习，`train-detector` 是 YOLO 视觉模型训练。下载、理解和离线视觉训练命令不会创建游戏输入控制器。

- [架构与模块边界](docs/architecture.md)
- [插件开发、视频理解与真实游戏接入](docs/plugins.md)
- [记忆与训练流程](docs/learning.md)
- [GPT-6 技能适配检查](docs/skills-audit.md)
- [仅本项目使用的技能](.agents/skills/game-agent-gpt6/SKILL.md)
- [验证结果与限制](docs/validation.md)

其他命令：

```bash
python -m game_agent plugins
python -m game_agent ingest examples/shop-tutorial.json --output memory/parsed-plan.json
python -m game_agent run --plan memory/parsed-plan.json
python -m game_agent export --output memory/datasets/verified.jsonl
python -m unittest discover -s tests -v
```

每条运行命令输出 run_id、状态和测量到的 tick P95。模拟耗时不能代替实机延迟；只有发送过动作并观察到成功的对应模式轨迹才作为可学习经验。

## 环境

已验证环境：

- Python 3.12
- PyTorch 2.11.0 + CUDA 12.8
- Ultralytics 8.4.144
- NVIDIA GeForce RTX 5070 Ti Laptop GPU（12GB）

## Conda / Miniforge 配置

建议使用 Miniforge 管理独立的 Python 环境。它可以安装在当前用户目录，不需要 `sudo`，也不会替换 Arch Linux 由 `pacman` 管理的系统 Python。

### 1. 安装 Miniforge

Linux x86_64 可以执行：

```bash
cd /tmp
curl -L -o Miniforge3.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3.sh
```

安装时建议使用默认目录 `~/miniforge3`，并允许安装程序执行 `conda init`。

如果安装后当前终端仍然找不到 `conda`，执行：

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda init bash
source ~/.bashrc
```

如果不希望每次打开终端时自动进入 `base` 环境：

```bash
conda config --set auto_activate_base false
```

### 2. 创建 YOLO26 环境

```bash
conda create -n yolo26 python=3.12 -y
conda activate yolo26
python -m pip install --upgrade pip
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
```

这里的 PyTorch 安装命令适用于本项目已验证的 CUDA 12.8 环境。如果显卡驱动或 CUDA 版本不同，请根据 PyTorch 官方安装页面选择对应命令。

### 3. 验证环境

```bash
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA 可用:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '无')"
python -c "import ultralytics; print('Ultralytics:', ultralytics.__version__)"
```

正常情况下，第一条命令会显示 `CUDA 可用: True` 和本机 NVIDIA GPU 名称。

### 4. 常用 Conda 命令

```bash
# 进入项目环境
conda activate yolo26

# 退出当前环境
conda deactivate

# 查看所有环境
conda env list

# 删除并重建环境（排查依赖冲突时使用）
conda remove -n yolo26 --all
```

通用 Ultralytics `yolo26*.pt` 权重默认不存入仓库，首次运行时可能自动下载。经过大小、来源和验证结果核对的原神教程基线是明确例外，保存在 `models/genshin-ui-yolo26n-v1.pt`；它没有通过跨视频泛化验收，限制见[模型说明](models/README.md)。

## 运行图片检测

```bash
python yolotest.py
```

`yolotest.py` 使用 `yolo26s.pt`、`imgsz=1280` 检测 `people_2k.jpg`。脚本先预热 GPU，再执行 30 次测量，输出：

- JPEG 解码时间
- 预处理、GPU 推理和后处理时间
- 模型处理 P50/P95
- 包含 JPEG 解码的完整流程 P50/P95

检测结果写入 `runs/predict/people_2k_result.jpg`。

## 筛选模型

```bash
python benchmark_yolo26.py
```

基准程序使用同一张 2560×1440 图片，对 YOLO26 n/s/m/l 分别测试 `640`、`1280`、`1920`、`2560` 输入尺寸。每个组合预热 5 次、测量 30 次，以端到端 P95 不超过 30ms 作为速度筛选条件。

本机共享 GPU 环境中的实测候选：

| 模型与输入尺寸 | 模型处理 P95 |
| --- | ---: |
| YOLO26s / 1280 | 10.65 ms |
| YOLO26m / 1280 | 27.38 ms |
| YOLO26n / 1920 | 12.04 ms |
| YOLO26n / 2560 | 28.45 ms |

实际部署仍需用目标数据集比较召回率和误检率。视频或摄像头帧应直接以内存图像传入，避免逐帧 JPEG 编解码。

## 测试图片

`people_2k.jpg` 来源于 Sebastian Mellen 在 Unsplash 发布的照片：

https://unsplash.com/photos/a-crowd-of-people-in-a-street-2AA-aU58l2E

图片按 Unsplash License 使用。

## 相关文档

- YOLO26：https://docs.ultralytics.com/models/yolo26/
- 模型训练：https://docs.ultralytics.com/modes/train/
- 视频跟踪：https://docs.ultralytics.com/modes/track/
- 模型导出：https://docs.ultralytics.com/modes/export/
