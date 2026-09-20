# 第一阶段：下载、分类、理解视频

本阶段回答“视频讲了什么、画面在做什么”。下载只保存原始媒体和分类；理解时在内存中采样画面、识别语音，再输出中文语义，不生成游戏按键计划。

## 安装与命令

```bash
conda activate yolo26
bash tools/setup-video.sh
.venv/bin/python tools/fetch-video-models.py
./tools/video doctor
./tools/youget '视频网页或媒体 URL'
./tools/video videos
./tools/video classify 视频编号 gameplay
./tools/video understand 视频编号
./tools/video understand /完整路径/教程.mp4
./tools/video understand 视频编号1 视频编号2
./tools/video add-video /完整路径/教程.mp4
```

`.venv` 复用当前 Conda 环境的 PyTorch/CUDA，模型及下载缓存放在项目 `memory/`。不修改系统 Python、全局技能或全局模型目录。模型准备命令会联网下载约 5 GB。后续 `understand` 使用本地权重，`local_files_only=True` 禁止缺少权重时自动下载。

`./tools/video` 自动使用项目环境和 `configs/video.toml`。在装有依赖的环境里，也可执行 `python -m game_agent download URL` 或 `python -m game_agent understand PATH`，视频命令自动选择视频配置。批量理解在同一进程复用模型。

`./tools/youget URL` 等价于 `./tools/video download URL`。

## 原始媒体和分类

分类包括 `tutorial`（视频教程，默认）、`gameplay`（游戏实录）、`reference`（参考资料）、`other`（其他）。默认分类来源为 `default`，表示用户设定的默认值，不表示模型已确认内容。重复入库保留已有人工分类。

下载器使用 `--no-merge --no-caption`，不主动剪辑、转码、拼接或下载弹幕/字幕侧文件。[you-get 官方说明](https://github.com/soimort/you-get)

ffprobe 只读取媒体信息。只有下载成功且存在可读取视频流才入库，原文件保存 SHA-256 校验值。常见的“一条视频流 + 一条独立音频流”会在理解时分别读取，不生成合并文件。多段视频分别生成报告；暂不推断分段连续性或全片时间线。精确配对可用单个视频路径和 `--audio 音频路径`。

下载清晰度采用站点默认值，可在 `plugins.downloader.options.stream` 指定 you-get 的 stream ID。站点改版、登录限制或不支持的站点仍可能导致下载失败，以工具实际结果为准。

### 登录视频和 Bilibili 多分P

项目内的 Cookie 文件统一放在 `memory/auth/`，该目录随本机项目数据保存并被 Git 忽略。把 Chrome 登录状态导出为 Netscape 格式后，保存到：

```text
memory/auth/bilibili-cookies.txt
```

Cookie 相当于登录凭证，只保留当前用户读写权限：

```bash
chmod 600 memory/auth/bilibili-cookies.txt
```

当前 `./tools/youget` 封装只接受单个 URL 和分类参数，尚未暴露原生 you-get 的 `--cookies`、`--playlist`。登录视频或同一 BV 的多分P使用项目环境中的原生命令。先读取全部分P和登录后可用的清晰度，不下载媒体：

```bash
.venv/bin/you-get \
  --playlist \
  --cookies memory/auth/bilibili-cookies.txt \
  --info \
  "https://www.bilibili.com/video/BV1P6SNYREo8/"
```

下载全部分P到项目本地目录，优先使用兼容性较好的 1080P AVC：

```bash
mkdir -p memory/import

.venv/bin/you-get \
  --playlist \
  --cookies memory/auth/bilibili-cookies.txt \
  --format dash-flv-AVC \
  --output-dir memory/import \
  "https://www.bilibili.com/video/BV1P6SNYREo8/"
```

需要 1080P60 时将格式改为 `dash-flv_p60-AVC`。格式名称以带 Cookie 的 `--info` 实际输出为准，并非所有视频都提供相同清晰度或编码。下载完成后，如需写入项目分类库，对每个合并完成的视频运行：

```bash
./tools/video add-video "/完整路径/某个分P.mp4" --category tutorial
```

直接把 Chrome 的 `Default/Cookies` 数据库传给 you-get 无效：Chrome 使用加密的 `cookies` 表，而当前 you-get 只直接读取 Netscape `cookies.txt` 或 Firefox `moz_cookies` SQLite。不要提交、分享或在命令输出中打印 Cookie 内容。

```text
memory/videos/
  catalog.sqlite3                分类、来源和校验值
  objects/<视频编号>/raw/          原始视频/音频流
  cache/hashes/                  文件校验缓存
  cache/speech/                  语音时间段缓存
  reports/<内容与配置摘要>.json    完整语义及测量值
  reports/<内容与配置摘要>.md      可阅读的中文报告
```

运行数据默认 Git 忽略。改分类只更新 SQLite，不修改原始文件。直接理解外部文件不会复制它，需要归档时运行 `add-video`。

## 模型与输出

视觉插件默认使用本地 [Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)，通过附有时间标记的采样画面理解内容。语音使用本地 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) small，默认 CPU int8、4 线程、beam size 1、VAD；可分别替换插件。

每个语义段包含摘要、观察事实、可能的操作目的、不确定内容和程序记录的采样时间。结果是 `candidate_understanding`，不能作为可靠按键标签或已学会的游戏技能。时间段由采样位置划分，不是精确的事件起止点。教程中的文本是待分析数据，不会被执行。

有音轨默认识别完整音轨，无音轨标记 `absent`。可以显式只读画面，或提供现成文字节省语音推理：

```bash
./tools/video understand 视频编号 --visual-only
./tools/video understand 视频编号 --transcript /完整路径/字幕.json
```

字幕 JSON 格式为 `[{"start_s": 0, "end_s": 3.5, "text": "先打开商店"}]`；也支持 UTF-8 纯文本，但不声称它已经逐句对齐。每个视觉段最多引入 12000 个语音字符，超出会标记截断，完整转录仍保存。仅画面模式会声明无法复述声音中的讲解。

## 提速和测量

| 模式 | 全片采样上限 | 每批帧数 | 输入最长边 | 每批输出 token 上限 |
|---|---:|---:|---:|---:|
| fast（默认） | 12 | 12 | 448 | 700 |
| balanced | 32 | 8 | 672 | 1000 |
| detailed | 64 | 8 | 896 | 1400 |

```bash
./tools/video understand 视频编号 --preset balanced
./tools/video understand 视频编号 --preset detailed
./tools/video understand 视频编号 --refresh
```

采样均匀覆盖整段时间轴，不按视频总帧数逐帧运行视觉模型。画面只在内存缩小，不中转 JPEG。间隔不超过约一秒时复用当前解码器向前读取，减少重复解码关键帧；间隔更大的稀疏帧直接跳转，长 GOP 仍可能带来额外开销。小字、短促操作或复杂长教程应提高精度，12 帧概览不保证找到所有步骤。

相同音频的转录跨视觉精度复用。语义缓存依据视频内容、模型文件版本戳、插件/依赖版本、采样设置、音频/字幕内容和报告 schema 失效。文件哈希缓存检查 inode、大小、修改时间和状态变更时间，减少反复扫描大视频。

报告分别记录读取/校验、解码缩放、语音处理、模型加载、预处理和推理时间，并输出处理耗时/视频时长。GPU 使用同步计时。`cache_hit` 和 `request_wall_s` 属于当前请求，`timings.total_uncached_s` 保留首次计算耗时；计时不包含 Python 进程启动。缓存时间不等于模型速度，完整视频语义也不等于 YOLO 单张检测耗时。

后续在同一批真实教程上比较摘要正确率、关键步骤召回、无法确认比例、总耗时和显存峰值。现已检查首个用户提供的 28 秒原神教程（Bilibili `BV1dt42147zq`）：fast 首次分析 12.58 秒，主题可识别，但自动初稿存在场景和委托完成状态误判。一个样本不足以评估整体准确率；经过 Codex 关键画面复核的结果保存在 `memory/videos/analysis/6235bf107aea1d29804a/reviewed.md`，该复核耗时不计入本地模型计时。

## 模块与兼容性

新增 `downloader.download`、`speech.transcribe/identity`、`semantic.describe/identity` 三个角色，由注册表延迟加载。接口在 `game_agent/video_contracts.py`。语义报告 schema v1、视频分类库 schema v1 与原来的 Plan、游戏记忆数据库独立。插件 API v1 做增量扩展，原八类插件仍兼容。

`video_library.py` 管原始文件和分类，`video_workflow.py` 管预算/缓存/报告，`video_cli.py` 管命令。替换下载器或模型时只改相应插件和 TOML，游戏控制循环保持兼容。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m game_agent demo
.venv/bin/python tools/check-video-pipeline.py
.venv/bin/python tools/check-video-pipeline.py --models
```

检查脚本用 12 秒、1280×720 的合成商店界面与英语合成讲解，实测 you-get 经过本机 HTTP 下载后的字节一致性。`--models` 运行真实本地视觉/语音模型，启用 Hub 离线模式与 Python 网络连接守卫；这不是整个操作系统的网络审计。结果保存在 `memory/validation/video-stage1/`，不混入正式教程目录。

合成输入仅用于功能和耗时检查，不能替代真实教程效果评估。脚本制作测试输入的编码步骤不属于用户视频下载流程。

2026-09-13 本机语音单独检查：12 秒合成视频（约 8.64 秒英语讲解），CPU int8 总耗时 1.96 秒，其中模型加载 0.40 秒、解码与转录 1.38 秒；转录包含打开商店、100 金币买剑、打开背包装备三步。记录见 `memory/validation/video-stage1/speech-check.json`。这是单个合成输入的观测值，不是中文真实教程的准确率或性能基准。

同一合成 H.264 视频的抽帧优化，预热后各测 5 次，中位数如下。全部固定最长边 448、关闭文件哈希计时，仅比较解码与缩放；32/64 帧行不是 balanced/detailed 整体配置的耗时。

| 采样帧数 | 原来每次跳转 | 优化后就近向前解码 | 倍数 |
|---|---:|---:|---:|
| 12 | 76.00ms | 26.54ms | 2.86× |
| 32 | 174.52ms | 46.70ms | 3.74× |
| 64 | 300.84ms | 87.49ms | 3.44× |

这些数据不含语音或视觉模型推理，不能当作完整语义延迟。采样帧与时间戳一致性有回归测试；详细测量见 `memory/validation/video-stage1/sampling-comparison.json`。真实长视频与不同 GOP 的收益需要另测。

### 完整本地语义实测

Qwen3-VL-2B 使用本机 RTX 5070 Ti Laptop GPU，faster-whisper small 使用 CPU。视觉权重 SHA-256 与官方发布文件一致；模型均已准备到本项目，`./tools/video doctor` 通过。

当时用于 12 秒合成视频验证的语义插件为 `qwen3.semantic` 1.0.2。相同视频、fast 模式的单次检查结果如下；不含 Python 进程启动时间，未清空操作系统文件缓存。

| 场景 | 总耗时 |
|---|---:|
| 本进程首次加载模型并读取语音/画面 | 8.10 秒 |
| 复用模型，重新执行语音和视觉推理 | 4.57 秒 |
| 相同输入命中语义缓存 | 30.8ms |

复用模型时，视觉推理约 3.26 秒、语音处理约 1.22 秒。通过合并逐帧重复描述、限制快速模式篇幅，输出从初始实现的 565 tokens 降到 177 tokens；该样片复用模型的总耗时由 11.04 秒降至 4.57 秒。变化来自减少重复输出，不是硬件吞吐提升或经过统一数据集评估的准确率提升。

输出摘要为“教程演示了在游戏中的购买和装备武器的步骤”，并识别出 100 金币的剑。人工检查也发现了限制：部分观察句推断了画面没有显示的鼠标点击，且一次把 `SWORD EQUIPPED` 误读成 `WORLD EQUIPPED`。所以本阶段只完成了候选语义与性能流程，细节正确率尚未达到游戏动作真值的验收条件；真实教程效果仍需要用户视频验证。

完整计时、转录、输出路径和人工检查记录在 `memory/validation/video-stage1/result.json`，首次加载报告另存 `cold-report.json`。43 项单元测试、原有模拟任务和本地模型检查通过。合成素材的功能通过不等于真实游戏的准确率通过。

长视频真实运行后，语义插件升级到 1.0.4：所有精度统一限制单批 JSON 的摘要和数组长度；模型输出因 token 上限截断为不完整 JSON 时，自动扩大上限重试一次。报告中的 `provenance.semantic.version` 和 `timings.semantic_batches[].generation_attempts` 用于区分插件版本和实际生成次数。
