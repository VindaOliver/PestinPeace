from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
import requests

DEFAULT_CONFIDENCE = 0.25
DEFAULT_TIMEOUT = 30


def normalize_predict_url(url: str) -> str:
    u = url.strip().rstrip("/")
    if u.endswith("/predict"):
        return u
    return f"{u}/predict"


def capture_image(camera_index: int = 0, save_path: str = "capture.jpg") -> Path | None:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: cannot open camera index {camera_index}")
        return None

    # Warm-up frames reduce black/unstable first frame on some USB camera drivers.
    for _ in range(5):
        cap.read()
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Error: failed to capture frame.")
        return None

    out = Path(save_path)
    cv2.imwrite(str(out), frame)
    return out


def send_for_inference(image_path: Path, api_url: str, conf: float, timeout: int) -> dict | None:
    try:
        with image_path.open("rb") as f:
            files = {"image": (image_path.name, f, "image/jpeg")}
            params = {"conf": conf}
            response = requests.post(api_url, files=files, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"HTTP error: {exc}")
        return None
    except ValueError as exc:
        print(f"JSON parse error: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Raspberry Pi camera client for YOLO aphid detection.")
    parser.add_argument("--url", required=True, help="Container App base URL or /predict URL.")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--interval", type=int, default=0, help="Seconds between captures. 0 means single shot.")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE, help="Confidence threshold.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    parser.add_argument("--output", default="capture.jpg", help="Local capture image path.")
    args = parser.parse_args()

    api_url = normalize_predict_url(args.url)
    print(f"Using endpoint: {api_url}")

    while True:
        image_path = capture_image(camera_index=args.camera, save_path=args.output)
        if image_path is not None:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] Captured: {image_path}")
            result = send_for_inference(image_path=image_path, api_url=api_url, conf=args.conf, timeout=args.timeout)
            if result is not None:
                count = result.get("count", 0)
                print(f"Detected aphids: {count}")
                print(json.dumps(result, indent=2, ensure_ascii=False))

        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
