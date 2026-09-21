# 原神 YOLO 教程基线训练计划与进度

更新日期：2026-09-21。本计划把本地教程视频制作成一个可复现的视觉基线，用于验证 Linux 训练产物能否迁移到 Windows 实时感知链路。该模型不是正式实机模型；目标 Windows 录像尚未提供，不能用教程指标替代实机准确率。

## 本轮范围

训练集使用短教程 `BV1dt42147zq`，验证集使用内容和文件均独立的系列教程 P10、P13。数据按完整录制来源分组，不把同一视频的相邻帧拆到训练和验证集合。

第一版类别：

| 类别 | 作用 | 独立验证正样本 |
|---|---|---|
| `hud_minimap` | 判断正常探索 HUD | P10、P13 |
| `interaction_prompt` | 定位当前可交互提示 | P10 |
| `inventory_panel` | 判断背包界面 | P13 |
| `quest_tab` | 定位背包任务页签 | 暂无 |
| `quest_item_card` | 定位任务物品卡片 | 暂无 |
| `use_button` | 定位可用的使用按钮 | 暂无 |
| `achievement_banner` | 检测短时成就弹窗 | 暂无 |
| `dialogue_box` | 判断底部剧情/派蒙对话 | 暂无 |

没有独立正样本的类别只检查训练流程和验证集误报，不能报告为已验证召回。动态任务名称和进度不属于这些类别，后续由 OCR 与跨帧状态融合处理。

## 节点进度

| 节点 | 状态 | 输入 | 完成条件 | 证据/输出 |
|---|---|---|---|---|
| GY0 范围与类别冻结 | 已完成 | 实时感知方案、短教程时间线 | 类别含义和证据边界写入文档 | 本文、本项目实时感知方案 |
| GY1 素材与隔离检查 | 已完成 | `BV1dt42147zq`、P10、P13 | 训练/验证使用不同源哈希和录制组 | 短教程 28.03 秒；P10/P13 独立文件 |
| GY2 训练帧抽取与复核 | 已完成 | 短教程 | 每帧人工核对，目标框或明确负样本，`reviewed=true` | 33帧；`memory/datasets/genshin-ui-baseline-train-v1/` |
| GY3 验证帧抽取与复核 | 已完成 | P10、P13 | 独立录制的正/负样本完成复核 | 19帧；`memory/datasets/genshin-ui-baseline-val-v1/` |
| GY4 数据集构建与静态校验 | 已完成 | GY2、GY3 | 无录制/源/图片跨集合泄漏，YOLO 数据可校验 | train=33、val=19；`memory/datasets/genshin-ui-yolo-v1/` |
| GY5 YOLO26n 基线训练 | 已完成 | GY4、本地 `yolo26n.pt` | 产生 `best.pt`、训练记录和哈希 | 50轮；版本化权重 `models/genshin-ui-yolo26n-v1.pt` |
| GY6 独立帧与完整教程回放 | 已完成，泛化未通过 | GY5 | 保存逐类结果、误报、漏检和限制 | `docs/reports/genshin-ui-yolo26n-v1-evaluation.json` |
| GY7 Windows 迁移准备 | 已完成 | GY5、GY6 | 配置示例指向权重，记录 Windows dry-run 步骤 | `configs/genshin-windows.example.toml`；本机迁移包已生成并校验 |

状态只按实际产物更新：`待执行 → 进行中 → 已完成/受阻`。训练命令成功不等于模型通过 GY6，Linux 视频回放成功也不等于 Windows 实机验收。

## 标注约定

- 坐标使用当前帧 0–1 归一化 `xyxy`。
- 界面切换动画中仅标注已经清晰出现的对象。
- `inventory_panel` 表示背包主体界面，不把普通游戏 HUD 标成背包。
- `quest_item_card` 只框单个任务道具卡片；文字含义不从图标猜测。
- `use_button` 只标可执行状态，禁用或正在消失的按钮作为负样本。
- `achievement_banner` 只标底部短时弹窗，不把成就列表页标成弹窗。
- `dialogue_box` 框底部角色名与正文区域；视频作者字幕和贴纸不标。
- 每帧检查所有八类后才设置 `reviewed=true`；空框表示明确负样本。

## 训练配置

第一轮使用本地 `yolo26n.pt`，避免在小数据集上先投入大模型：

```text
epochs = 50
imgsz = 640
batch = 8
workers = 0
device = 0（CUDA 不可用时记录实际回退或停止）
seed = 0
```

训练保持离线，输出目录不可覆盖。若数据量不足导致指标异常，只增加经过复核的独立素材，不通过复制帧或把同源帧放入验证集提高分数。

## 验收方式

本轮基线至少完成以下检查：

1. 数据集构建器确认 train/val 来源隔离，图片与标注哈希一致。
2. 训练产生可加载的 `best.pt` 和 `training.json`。
3. 对独立 P10/P13 帧逐张保存预测结果；分别列出三类已有正样本的召回和所有类别的误报。
4. 对完整 28 秒短教程回放，记录每一类首次出现、连续检测和消失情况。
5. 将权重用于现有 `yolo.perception` 配置时只输出可观测视觉事实；不把教程上下文推断写成 YOLO 检测。

正式 Windows 使用前仍需增加目标分辨率、UI 缩放、语言和游戏 build/profile 下的录制，重新独立验证。TensorRT 引擎在目标 Windows/GPU 上导出；本轮只交付 PyTorch `.pt`。

## 2026-09-21 基线结果

本轮在 RTX 5070 Ti Laptop GPU 上完成 YOLO26n、640 输入、batch 8、50轮训练。训练产物状态为 `trained_not_game_verified`。权重以 `models/genshin-ui-yolo26n-v1.pt` 提交，大小为5,368,901字节（约5.12 MiB），SHA-256 为 `efb5ac03ae65550229678677a04b8e4b6a1094631cfc4590c1a1740a110530ca`。训练元数据和逐帧评估分别保存为 [`genshin-ui-yolo26n-v1-training.json`](reports/genshin-ui-yolo26n-v1-training.json) 与 [`genshin-ui-yolo26n-v1-evaluation.json`](reports/genshin-ui-yolo26n-v1-evaluation.json)。

Ultralytics 汇总的独立验证指标为 precision 0.9849、recall 0.3333、mAP50 0.3511、mAP50-95 0.3393。这个汇总只覆盖验证集中有正样本的三个类别，不能代表八类模型能力：

| 类别 | 独立正样本 | conf=0.25、IoU=0.5 结果 | 判断 |
|---|---:|---|---|
| `hud_minimap` | 16 | TP=0，FN=16，recall=0 | 不同视频的地图尺寸与作者布局差异导致泛化失败 |
| `interaction_prompt` | 2 | TP=0，FN=2，recall=0 | 样本不足，泛化失败 |
| `inventory_panel` | 1 | TP=1，FP=1，recall=1、precision=0.5 | 能识别独立背包帧，但把成就列表页误判为背包 |
| 其余五类 | 0 | 只能检查误报，不能计算独立召回 | 未验证 |

对训练来源的完整28秒教程回放显示：小地图、背包、任务页、任务物品和对话区域形成了时间连续的检测；交互提示、使用按钮和成就弹窗在 conf=0.25 下仍未检出。随机抽取的22.898秒画面从通用 COCO 权重的无相关检测，提升为 `dialogue_box` 0.448，但这是训练来源画面，只说明模型记住了该视觉模式。

结论：GY5 已证明教程数据可以生成可在 Windows 加载的 `.pt` 权重，GY6 同时证明当前33帧不能形成可用的跨视频实时模型。下一轮不调低阈值掩盖漏检，优先增加目标 Windows profile 的独立正样本，并把作者叠加层和不同 UI 缩放作为明确的数据域。

训练启动时 Ultralytics 8.4.144 自动下载了一个 `Arial.ttf` 字体到项目本地配置目录；初始权重、视频、标注和训练数据均为本地文件。字体随后已缓存，但本轮不能描述为完全无网络训练。后续离线复验应预先准备字体并启用网络阻断。

Windows 迁移包为本机 `memory/transfers/genshin-ui-yolo26n-v1-windows.zip`，包含228个文件、84,031,007字节，SHA-256 为 `cfb067687fdd4a38f8c3ba0c6aa2b8bee2cd3258751c9bbe3b2adf66e92fd3d5`；压缩包完整性检查通过。配置仍保持 `dry-run.controller`，该包只用于 Windows 加载、截图和识别检查，不能据此开启真实输入。
