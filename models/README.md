# 版本化模型

## `genshin-ui-yolo26n-v1.pt`

- 文件大小：5,368,901 字节（约 5.12 MiB）
- SHA-256：`efb5ac03ae65550229678677a04b8e4b6a1094631cfc4590c1a1740a110530ca`
- 模型：YOLO26n，输入 640，8 类原神界面对象
- 训练数据：短教程的 33 张已复核帧
- 独立验证：P10/P13 的 19 张已复核帧
- 状态：`trained_not_game_verified`

该权重用于复现教程视觉基线和验证 Linux 到 Windows 的模型加载链路。它在独立录像上未通过泛化验收：小地图和交互提示召回为 0，背包类别有误报；不要用它驱动真实游戏输入。

训练元数据见 [`docs/reports/genshin-ui-yolo26n-v1-training.json`](../docs/reports/genshin-ui-yolo26n-v1-training.json)，逐帧评估见 [`docs/reports/genshin-ui-yolo26n-v1-evaluation.json`](../docs/reports/genshin-ui-yolo26n-v1-evaluation.json)，训练计划与限制见 [`docs/genshin-yolo-training-plan.md`](../docs/genshin-yolo-training-plan.md)。
