from pathlib import Path
from statistics import mean, median
from time import perf_counter

import cv2
import numpy as np
import torch
from ultralytics import YOLO


project_dir = Path(__file__).resolve().parent
model_path = project_dir / "yolo26s.pt"
image_path = project_dir / "people_2k.jpg"
output_path = project_dir / "runs" / "predict" / "people_2k_result.jpg"

# 推荐的精度/速度平衡配置：读取原始 2560x1440 图片，送入模型时将
# 最长边缩放到 1280。若要接近原始 2K 尺寸推理，可改为 2560，
# 但 yolo26s 在本机上不能稳定满足 30 ms 要求。
input_size = 1280
warmup_runs = 5
measure_runs = 30

if not image_path.is_file():
    raise FileNotFoundError(f"请把待检测图片放到：{image_path}")
if not torch.cuda.is_available():
    raise RuntimeError("本脚本测量 CUDA GPU 性能；请先安装与显卡驱动匹配的 GPU 版 PyTorch。")

# 仓库不保存体积较大的模型权重；本地不存在时由 Ultralytics 自动下载。
model = YOLO(model_path if model_path.exists() else model_path.name)

# GPU 第一次运行会初始化 CUDA 和模型内核，时间明显偏高，因此先预热，
# 预热数据不计入最终结果。
# 用文件字节解码，兼容 Windows 下带中文的项目目录。
warmup_image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
if warmup_image is None:
    raise RuntimeError(f"图片读取失败：{image_path}")

for _ in range(warmup_runs):
    model.predict(
        source=warmup_image,
        imgsz=input_size,
        device=0,
        conf=0.25,
        verbose=False,
    )

decode_times = []
predict_times = []
total_times = []
preprocess_times = []
inference_times = []
postprocess_times = []

for _ in range(measure_runs):
    # 同步 GPU 后开始计时，确保上一次推理已经结束。
    torch.cuda.synchronize()
    total_started = perf_counter()

    decode_started = perf_counter()
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    decode_times.append((perf_counter() - decode_started) * 1000)

    predict_started = perf_counter()
    result = model.predict(
        source=image,
        imgsz=input_size,
        device=0,
        conf=0.25,
        verbose=False,
    )[0]
    torch.cuda.synchronize()

    predict_times.append((perf_counter() - predict_started) * 1000)
    total_times.append((perf_counter() - total_started) * 1000)

    # Ultralytics 对模型处理阶段给出的分项时间，不包含 JPEG 文件读取。
    preprocess_times.append(float(result.speed["preprocess"]))
    inference_times.append(float(result.speed["inference"]))
    postprocess_times.append(float(result.speed["postprocess"]))

# 保存最后一次检测的可视化结果；保存图片的耗时不计入识别时间。
output_path.parent.mkdir(parents=True, exist_ok=True)
result.save(filename=str(output_path))

print(f"图片：{image_path.name}，尺寸：{warmup_image.shape[1]}x{warmup_image.shape[0]}")
print(f"模型：{model_path.name}，imgsz={input_size}，测试次数：{measure_runs}")
print(f"JPEG 解码平均：{mean(decode_times):.2f} ms")
print(f"预处理平均：{mean(preprocess_times):.2f} ms")
print(f"GPU 推理平均：{mean(inference_times):.2f} ms")
print(f"后处理平均：{mean(postprocess_times):.2f} ms")
print(f"模型处理 P50/P95：{median(predict_times):.2f}/{np.percentile(predict_times, 95):.2f} ms")
print(f"完整流程 P50/P95：{median(total_times):.2f}/{np.percentile(total_times, 95):.2f} ms")
print(f"结果图片：{output_path}")
