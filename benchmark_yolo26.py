"""在本机 GPU 上筛选满足单张图片延迟目标的 YOLO26 模型。"""

from pathlib import Path
from statistics import mean, median
from time import perf_counter

import cv2
import numpy as np
import torch
from ultralytics import YOLO


PROJECT_DIR = Path(__file__).resolve().parent
IMAGE_PATH = PROJECT_DIR / "people_2k.jpg"
# 本次实测已下载完成的模型。x 权重下载过慢，暂不纳入本轮筛选。
MODEL_NAMES = ["yolo26n.pt", "yolo26s.pt", "yolo26m.pt", "yolo26l.pt"]
TARGET_MS = 30.0
WARMUP_RUNS = 5
MEASURE_RUNS = 30


def percentile(values: list[float], percent: float) -> float:
    return float(np.percentile(values, percent))


def benchmark(model_name: str, image: np.ndarray, imgsz: int) -> dict[str, float | str | int]:
    """预加载图片后计时；端到端时间包含预处理、推理和后处理，不含磁盘读取。"""
    model_path = PROJECT_DIR / model_name
    model = YOLO(model_path if model_path.exists() else model_name)

    for _ in range(WARMUP_RUNS):
        model.predict(source=image, imgsz=imgsz, device=0, verbose=False)

    wall_times: list[float] = []
    preprocess_times: list[float] = []
    inference_times: list[float] = []
    postprocess_times: list[float] = []

    for _ in range(MEASURE_RUNS):
        torch.cuda.synchronize()
        started = perf_counter()
        result = model.predict(source=image, imgsz=imgsz, device=0, verbose=False)[0]
        torch.cuda.synchronize()
        wall_times.append((perf_counter() - started) * 1000)
        preprocess_times.append(float(result.speed["preprocess"]))
        inference_times.append(float(result.speed["inference"]))
        postprocess_times.append(float(result.speed["postprocess"]))

    return {
        "model": model_name,
        "imgsz": imgsz,
        "pre_ms": mean(preprocess_times),
        "infer_ms": mean(inference_times),
        "post_ms": mean(postprocess_times),
        "wall_median_ms": median(wall_times),
        "wall_p95_ms": percentile(wall_times, 95),
        "pass": "PASS" if percentile(wall_times, 95) <= TARGET_MS else "FAIL",
    }


def print_result(result: dict[str, float | str | int]) -> None:
    print(
        f"{result['model']:<12} imgsz={result['imgsz']:<4} "
        f"pre={result['pre_ms']:>6.2f} ms  "
        f"infer={result['infer_ms']:>6.2f} ms  "
        f"post={result['post_ms']:>6.2f} ms  "
        f"wall-p50={result['wall_median_ms']:>6.2f} ms  "
        f"wall-p95={result['wall_p95_ms']:>6.2f} ms  "
        f"{result['pass']}"
    )


def main() -> None:
    image = cv2.imread(str(IMAGE_PATH))
    if image is None:
        raise FileNotFoundError(f"无法读取测试图片：{IMAGE_PATH}")

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Image: {IMAGE_PATH} ({image.shape[1]}x{image.shape[0]})")
    print(f"Target: wall-clock P95 <= {TARGET_MS:.0f} ms\n")

    # imgsz 是送进神经网络的最长边。源图始终为 2560x1440；逐档测试能
    # 找到模型大小与小目标细节之间更合理的性能平衡点。
    for imgsz in (640, 1280, 1920, 2560):
        print(f"\nInput-size screening: imgsz={imgsz}")
        for model_name in MODEL_NAMES:
            print_result(benchmark(model_name, image, imgsz=imgsz))


if __name__ == "__main__":
    main()
