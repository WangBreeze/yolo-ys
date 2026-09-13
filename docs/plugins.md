# 插件开发与真实游戏接入

## 最小插件

在一个可导入的 Python 模块里实现角色协议。例如单独发布 `my_game_policy.py`：

```python
from game_agent.contracts import Action

class MyPolicy:
    API_VERSION = 1
    ROLE = "policy"
    VERSION = "1.0.0"

    def __init__(self, context, options):
        self.options = options

    def choose(self, step, state):
        return Action(kind="key", key="E", duration_ms=50)

    def close(self):
        pass
```

此例只演示接口，不是通用决策逻辑。创建项目内清单 `plugins/my-game.toml`：

```toml
[[plugins]]
id = "my-game.policy"
role = "policy"
version = "1.0.0"
api_version = 1
factory = "my_game_policy:MyPolicy"
```

新增配置文件：

```toml
extends = "demo.toml"
plugin_manifests = ["plugins/my-game.toml"]

[plugins.policy]
use = "my-game.policy"
```

从项目目录 `python -m game_agent --config configs/my-game.toml doctor`。可导入模块可以位于项目根目录，也可以通过当前 Conda 环境中的独立 Python 包提供。`doctor` 检查已知依赖和配置，真正创建时还会验证插件类的版本与方法。插件在当前 Python 进程运行，不提供不受信代码沙箱。

## 接入具体游戏

Windows 接入从 `configs/windows.example.toml` 与 `windows-info` 开始，使用 `windows.capture` / `windows.controller`，步骤见 [双平台说明](windows-linux.md)。下面的 Hyprland 配置保留给 Linux 桌面实验；当前用户的 Linux 工作流使用离线训练配置。

1. 复制 `configs/hyprland.example.toml` 为本机配置，填写游戏、版本、键位/UI profile；用 `hyprctl -j activewindow` 获取实际窗口 class。
2. 准备当前游戏的本地检测模型，配置 labels 映射，使输出事实和教程 `pre/post/success` 同名。原始 COCO 权重不能直接识别“商店已打开”“武器已装备”等游戏语义。
3. 配置对应的感知插件。YOLO 目前提供类别出现/消失和归一化目标框；OCR、目标跟踪、血量估计或组合状态需要替换/扩展 perception 插件。
4. 用人工标注 JSON 先验证游戏的步骤和成功条件，再引入视频模型自动生成候选计划。
5. 先用 dry-run 控制器验证定位与计划；实机执行使用 `--live`。如果没有可辨识的成功条件，先补感知和标注。

本机可选依赖：

```bash
conda activate yolo26
python -m pip install -e '.[vision,linux]'
# 只有启用本地视频语言模型/语音识别才需要：
python -m pip install -e '.[vlm,asr]'
```

GPU 版 torch 安装沿用 README 中的 Conda 环境。Hyprland 后端需要已有 `hyprctl`、`grim` 及用户对 `/dev/uinput` 的访问权限。框架不修改系统权限、驱动或全局桌面配置；窗口截图和 uinput 在真实桌面上仍需集成验证。

## 视频理解

手工整理的视频步骤可以直接导入：

```bash
python -m game_agent ingest examples/shop-tutorial.json --output memory/parsed-plan.json
```

自动理解使用 `qwen-video.tutorial`。在游戏配置中提供本地完整 Qwen2.5-VL 模型目录、`observable_facts` 和按键 `bindings`，再运行：

```bash
python -m game_agent --config configs/my-game.toml ingest memory/videos/tutorial.mp4 --output memory/tutorial-plan.json
python -m game_agent --config configs/my-game.toml run --plan memory/tutorial-plan.json --live
```

两条命令分别表示理解和执行；导入命令本身不会操作游戏。模型目录必须已在本机，插件使用 `local_files_only=True`；不默认调用在线 API。当前实现按照时间均匀抽取最多 64 帧，适合短视频或已切分的教程。长视频需要先按技能切段，稀疏采样不保证捕获快速操作。

可提供现成字幕/转录 `transcript`，或者本地 Whisper 权重 `whisper_weights`（需 ffmpeg 和 asr extra）。未配置时只分析画面，来源明确记录为 `not_transcribed`。候选计划经过结构校验，未知键位或不可观察的状态会报错；视频本身通常不能唯一恢复真实键鼠时序。参见 [Qwen2.5-VL 模型卡](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct) 和 [Whisper](https://github.com/openai/whisper)。

## 录像读取

```bash
python -m game_agent inspect-video memory/videos/tutorial.mp4 --frames 16
python -m game_agent --config configs/video-replay.toml doctor
```

`inspect-video` 实际解码采样帧并返回帧数、时长、时间点和文件哈希，只报告视频元信息。`video.capture` 可将逐帧数据送给感知插件进行录像测试；它不是当前游戏窗口，不能与实机控制器组合。

## 升级与回滚

兼容实现升级：只更新插件实现、清单 version，并运行该插件测试和一次闭环回归。新增实现：添加模块与清单，用配置替换 `use`。回滚：恢复原清单/配置及模型文件。不要原地覆盖已经记录过哈希和版本的训练产物。

协议变更：先修改 `contracts.py` 并提升 API 版本，迁移受影响插件和持久化数据；不相关插件保持独立。可选模型和依赖缺失不应影响 demo、记忆检索和其他未使用该插件的流程。
