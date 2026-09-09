# YOLO26 本机推理与性能测试

这个项目使用 Ultralytics YOLO26 在 NVIDIA GPU 上进行图片检测，并测试 2K 图片从 JPEG 解码到检测完成的端到端延迟。

## 环境

已验证环境：

- Python 3.12
- PyTorch 2.11.0 + CUDA 12.8
- Ultralytics 8.4.144
- NVIDIA GeForce RTX 5070 Ti Laptop GPU（12GB）

建议使用 Miniforge 创建独立环境：

```bash
conda create -n yolo26 python=3.12 -y
conda activate yolo26
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
```

模型权重没有存入仓库。首次运行时，Ultralytics 会自动下载所需的 `yolo26*.pt` 文件。

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
