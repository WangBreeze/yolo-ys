# 项目记忆

## 2026-09-13：通用框架初版

用户目标：在本目录实现可替换插件的游戏视频模仿框架，持久记忆学习内容，创建非全局 GPT-6 项目技能。

决定：采用 Python 3.11+ 标准库核心、版本化数据协议、TOML 配置和 SQLite；可选的 YOLO、视频模型、Hyprland/uinput 仅按需加载。一次执行使用独立插件实例。以语义步骤和当前状态闭环执行，不按视频绝对时间机械重放。

已验证：动作驱动的商店模拟器可完成打开商店、购买和装备；数据库可跨重启回忆；动作经验表训练后能作为替换策略完成同一任务。28 项测试通过，覆盖插件替换、模式/游戏隔离、执行清理、失焦、过期/重复画面和本地视频解码。YOLO 插件使用已有权重在本机 GPU 推理成功；检查阻断网络连接。完整记录见 `docs/validation.md`。

限制：尚未指定真实游戏和教程，未进行真实窗口输入验收。Qwen2.5-VL/Whisper 需要本地权重和可选依赖，尚未实测其理解效果。动作经验学习不等于神经网络训练；屏幕像素加人工键鼠数据录制、OCR/跟踪融合、组合键/手柄和持久 PipeWire 采集属于后续适配。

后续工作从 `docs/architecture.md`、`docs/plugins.md` 和对应角色接口开始。增加游戏时更新 game/version/profile；改变插件时保留其他模块接口。测试和性能结论区分模拟、录像和实机。

## 2026-09-13：第一阶段视频库与语义读取

用户要求：项目内配置 you-get，默认下载视频教程；下载阶段只保留原文件并分类，随后独立读取语义，优先提高理解速度。

实现：新增 downloader、speech、semantic 三类 API v1 插件；`tools/youget` 默认下载并归类 tutorial，`tools/video understand` 读取编号或本地路径。原媒体、分类库、报告分别保存在 `memory/videos/objects`、`catalog.sqlite3`、`reports`。分类库和语义 schema 独立于游戏 Plan/SQLite，语义不直接进入已验证动作经验。

速度策略：fast 统一采样 12 帧并一次提交视觉模型，balanced/detailed 增加帧数和分批精度；内存解码缩放、批量模型复用、跨精度的语音缓存、内容/模型版本感知的语义缓存。分别记录首次计算与缓存读取时间，不把缓存结果冒充模型速度。

已验证：43 项单元测试及原模拟任务通过；使用真实 you-get 从本机 HTTP 下载合成的 12 秒、1280×720 商店教程，下载后的 SHA-256 与源文件一致。you-get 0.4.1743、Transformers 4.57.6、faster-whisper 1.2.1 已安装到项目 `.venv`，复用原 Conda CUDA/PyTorch。语音单独检查总耗时 1.96 秒；相同 12 帧的抽帧缩放中位耗时从 76.00ms 降至 26.54ms，采样结果保持一致。两者都不是完整语义延迟，测量范围见 `docs/video-stage1.md`。完整模型检查以 `memory/validation/video-stage1/result.json` 的实际记录为准。

未提供真实游戏教程，不能据合成素材宣称真实游戏理解准确率。配置、命令、采样和音频限制见 `docs/video-stage1.md`。当前项目技能继续适用于模块替换与本地记忆；第一阶段只输出候选语义，不要求先生成 Plan。

完整模型已就绪并实测：Qwen3-VL-2B 权重与官方 SHA-256 一致，faster-whisper small 已本地安装，doctor 通过。最终 semantic 插件 1.0.2 对 12 秒合成素材首次 8.10 秒、复用模型重算 4.57 秒、缓存 30.8ms（不含进程启动）。缩短重复描述后由初始 565 tokens 降至 177 tokens。已清理下载临时分段，保留本地模型及验证记录。

语义质量限制已实际观察到：摘要和 100 金币买剑/装备的主题可读出，但部分观察推断了未展示的点击，并误读过 WORLD EQUIPPED。不能声称完整细节理解已经验收；这些报告不能作为已执行动作的真值。检查结果与计时见 `memory/validation/video-stage1/result.json`，后续优先用用户真实教程建立准确率基线，再评估分辨率/模型替换。

## 2026-09-13：首个用户游戏教程分析

用户提供 Bilibili `BV1dt42147zq`，已用 you-get 下载并默认归类 tutorial，视频库编号 `6235bf107aea1d29804a`。原始 480P 视频与音频分别保存，28.03 秒，下载后校验值一致。

本地 fast 模式首次语义处理 12.58 秒（12 帧；语音 2.90 秒；视觉加载 2.34 秒、推理 4.24 秒），未命中缓存；不含进程启动和后续 Codex 画面复核。Qwen3-VL-2B 与 faster-whisper small 使用本地权重及 Hub 离线模式。

教程演示「餐品订单」送餐倒计时开始后，在背包「任务」页使用「美味的炸萝卜丸子」，约 20–21 秒出现「这不是应急食品」成就提示。片尾仅提示找莎拉重新领取餐品，未显示委托最终完成。Codex 复核发现自动初稿将户外摊位写成餐厅内，并过度推断委托已完成；原始模型输出保留未改写。复核说明、关键帧与自动语音字幕保存在 `memory/videos/analysis/6235bf107aea1d29804a/`，入口 `reviewed.md`。

这是一个真实教程样本的内容与耗时检查，不是整体准确率验收；未操作本机游戏，未写入已验证的动作经验。后续应评估短事件覆盖和小字识别，以及区分画面事实、作者建议与最终完成状态。

## 2026-09-13：Linux 视频训练与 Windows 部署适配

用户明确当前 Linux 只制作视频训练数据，游戏运行目标为 Windows。实现独立的 `windows.capture`（MSS 客户区采集）和 `windows.controller`（Win32 SendInput），带精确窗口匹配、线程级 DPI、窗口身份/几何/时效检查、短时输入、F12/STOP 与异常释放。Windows 示例默认 dry-run；当前环境未运行任何真实游戏输入。

新增 `prepare-dataset`、`build-dataset`、`check-dataset`、`train-detector`，detector_trainer 是可替换的 API v1 增量角色。标注和数据集独立 schema v1，不改变原 Plan/SQLite/动作学习语义。未复核帧禁止进入训练，同录制组/同视频/相同图片不能跨训练与验证集合。训练保存本地权重与数据哈希；新结果使用新目录。`experience.policy` 升级 1.0.1 修复 Windows UTF-8 加载，兼容原动作经验 schema v1。

提供 Windows CMD 和通用 Python 安装/运行入口、平台依赖标记、UTF-8 文件与中文图片路径修复、SQLite backup 和校验清单的跨平台 ZIP 打包工具。Linux `.venv` 不迁移到 Windows。入口文档 `docs/windows-linux.md`，离线配置 `configs/offline-training.toml`，Windows 模板 `configs/windows.example.toml`；保持原有 YOLO 基准用途。

已验证：68 项测试通过、原 demo/动作经验 train/learned-demo 通过。真实 CPU YOLO26n 单轮训练在两个合成录像的 4 张训练/4 张验证图上完成，函数耗时 2.49 秒，产物位于 `memory/validation/offline-training/`；指标为零，仅用于运行流程验证。Python socket.connect 守卫阻断网络，未做操作系统网络审计。

原神教程已抽出 32 个待标注帧到 `memory/datasets/genshin-food-v1/`，游戏信息对应 `configs/genshin-offline.toml`，build 记为未知；全部 reviewed=false、split=unassigned。实际执行 build 已确认拒绝未复核数据。尚无独立验证录像、人工键鼠采集或行为克隆训练，不能声称已训练出原神操作能力。GitHub Actions 双平台检查已配置，尚无远端运行验证结果；Windows 实机截图、输入兼容性、端到端延迟仍待目标环境验证。

## 2026-09-13：项目路线、开发 Wiki 与工作区整理

用户要求同步项目路线和开发 Wiki，缺失时创建，并提交当前工作区。此前已有架构、插件和分阶段使用文档，未有统一路线及 Wiki；本次新增 `docs/roadmap.md`、`docs/wiki/README.md`、`docs/wiki/development.md`，从根 README 导航，Wiki 随代码维护。

路线按框架、视频理解、Linux 视觉训练、Windows 接入、首个真实任务、人工示范/策略训练、多游戏复用划分；最近工作为标注规范、独立验证素材、正式视觉模型、Windows 原生检查、首个原神闭环。状态明确区分已实现、Linux 已验证与实机待验收。

`docs/validation.md` 从初版记录更新为当前 68 项回归、真实教程、合成训练和迁移证据汇总。历史 Windows 迁移包校验通过，但不含本次新增 Wiki；需要最新代码时重新打包。代码提交只纳入源文件、模板、测试、文档和项目记忆说明，大型视频/模型、运行数据库、环境及本机临时会话文件留在本机。

## 2026-09-20：纳塔 5.2 系列教程前 10 个分P解析

用户下载的 Bilibili `BV1P6SNYREo8` 前 10 个分P已在本机完成候选语义解析，共 7006.11 秒（1 小时 56 分 46 秒）。P1–P8 使用 fast（12 帧、1 段），P9–P10 使用 balanced（32 帧、4 段）；报告记录处理时间合计 325.35 秒，混合首次加载、热模型和语音缓存状态，不作为统一基准。汇总入口为 `memory/videos/analysis/BV1P6SNYREo8/first-10.md`。

内容上，P1 是路线和前置说明，P2 为浮羽之湾，P3–P9 为烟谜主连续收集路线，P10 转到花羽会并包含“勇士的每一面”和飞行挑战。语音中存在“神瞳/山头”“宝箱/保险”“涂鸦/图鸭”“传送锚点/传统帽点”等同音错词；fast 结果只适合主题筛选，不能恢复精确按键或完整路线。

长转录曾导致 Qwen 输出在 JSON 闭合前达到 token 上限。`qwen3.semantic` 升级到 1.0.4，统一要求紧凑 JSON，并在 JSON 解码失败时仅扩大生成上限重试一次；P9、P10 balanced 均以一次生成成功。语义仍是候选结论，未写入已验证动作经验。

P11–P20 随后全部使用 balanced 完成解析，共 6870.35 秒（1 小时 54 分 30 秒），报告计时合计 415.14 秒。10 个报告包含 40 个语义段，均由 1.0.4 一次生成成功。内容从花羽会延续到天蛇船和周边遗迹，最后以神像供奉、断片/石环、密藏和探索度说明收尾。第二批汇总位于 `memory/videos/analysis/BV1P6SNYREo8/last-10.md`，全 20 集入口为同目录 `all-20.md`。

全 20 个分P合计 13876.46 秒（3 小时 51 分 16 秒），报告计时合计 740.49 秒。该时间混合冷/热模型和语音缓存，只记录本次运行。后 10 集依然存在游戏专有词同音错误，报告用于主题检索和阶段定位，不能直接作为键鼠操作真值。

## 2026-09-20：教程第二阶段环境与边界

用户确认第一阶段可用，下一阶段把视频语音转成游戏命令。决定采用两级表示：先从带时间语音和画面证据生成 `semantic-command` 候选，再经人工复核编译为现有 Plan；不把旁白直接映射成固定按键或绝对坐标。现有 Plan/Step/Action、状态机、Windows 采集/控制和安全门继续复用。

当前 Linux 环境已满足离线候选命令生成；实际 Windows 执行仍需要真实游戏 build/profile、语言、分辨率/UI 缩放、键位、精确窗口身份、可观察事实和已验证感知模型。Action v1 只支持短时单键、左键点击、相对鼠标移动和等待，开放世界移动还需要按键保持/释放、组合输入和连续镜头控制。完整清单与验收门槛见 `docs/voice-command-stage2.md`。

原神 `semantic-command` schema v1、提取器、静态校验和 28 命令词典已经实现。词典参考本机 BetterGI 提交 `f29966868c6e2d5b8798bb6a4f3df201ec4a5f95` 的动作枚举、移动模式、动作处理器、按键释放和界面状态判断；BetterGI 保持只读且不是运行依赖。原始语音、起止时间、语义分段、模型来源和专有词纠错均保存在候选命令证据中，底层键名、绝对坐标和按键时长被 schema 禁止。

`BV1P6SNYREo8` 的 P1–P20 已在本机生成 674 条候选命令，54 条带纠错记录，逐文件静态校验通过；汇总为 `memory/commands/BV1P6SNYREo8/index.json`。P1 是前置说明，未生成执行命令。当前结果仍是规则命中候选，尚未人工复核或编译为 Plan，不能写入已验证动作经验，也不能用于真实输入。

本轮增加 5 项命令工作流测试后，项目共 73 项单元测试通过，原模拟 demo 继续成功。`list-commands`、P10 单集提取与校验、20 集逐文件校验和差异空白检查均通过。

GitHub Windows CI 暴露两项跨平台问题：未规范化的 `Context.root` 会让 Windows 临时目录中的合法输出被误判为越界；Windows 的 `st_ctime` 是创建时间，不能作为同大小、恢复 mtime 后的内容变化标记。输入/输出路径现在基于已解析的 root 做边界判断，Windows 摘要缓存改为重新计算内容哈希。新增两个回归测试后共 75 项测试及 demo 在 Linux 通过，等待远端 Windows CI 复验。
