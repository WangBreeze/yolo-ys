# YOLO26 本机推理与性能测试

这个项目使用 Ultralytics YOLO26 在 NVIDIA GPU 上进行图片检测，并测试 2K 图片从 JPEG 解码到检测完成的端到端延迟。

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
