from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DOCKERFILE_CODE = """FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    libglib2.0-0 \\
    libsm6 \\
    libxext6 \\
    libxrender1 \\
    libxcb1 \\
    libgl1 \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
COPY telemetry_dashboard.html /app/telemetry_dashboard.html
COPY local_web_client.html /app/local_web_client.html
COPY history_records.html /app/history_records.html
COPY model/best.pt /app/model/best.pt

EXPOSE 8000
ENV MODEL_PATH=/app/model/best.pt
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
"""


REQUIREMENTS_CODE = """fastapi==0.115.6
uvicorn[standard]==0.32.1
python-multipart==0.0.20
pillow==11.0.0
ultralytics==8.3.50
azure-storage-blob==12.24.0
azure-data-tables==12.5.0
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Docker context for YOLO26 inference (with IoT telemetry) and optionally build image.",
    )
    parser.add_argument(
        "--model",
        default="runs/detect/runs/train/yolo26_aphid_count3/weights/best.pt",
        help="Path to trained model checkpoint (.pt).",
    )
    parser.add_argument(
        "--context-dir",
        default=".container_yolo26",
        help="Output directory for Docker build context.",
    )
    parser.add_argument(
        "--server-template",
        default=".container_yolo26/server.py",
        help="Template server.py path to copy into build context.",
    )
    parser.add_argument(
        "--telemetry-dashboard-template",
        default="web_pages/telemetry_dashboard.html",
        help="Template telemetry dashboard HTML path to copy into build context.",
    )
    parser.add_argument(
        "--predict-web-template",
        default="web_pages/local_web_client.html",
        help="Template predict web client HTML path to copy into build context.",
    )
    parser.add_argument(
        "--history-web-template",
        default="web_pages/history_records.html",
        help="Template history records HTML path to copy into build context.",
    )
    parser.add_argument(
        "--image-tag",
        default="aphid-yolo26:latest",
        help="Docker image tag for build step.",
    )
    parser.add_argument(
        "--build",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Build docker image after generating context.",
    )
    parser.add_argument(
        "--platform",
        default="linux/amd64",
        help="Docker build platform.",
    )
    return parser.parse_args()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_model_path(model_path: Path) -> Path:
    if model_path.exists():
        return model_path

    cwd = Path.cwd()
    candidates = sorted(cwd.glob("runs/**/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Model not found: {model_path}")


def _resolve_template_path(path_str: str, script_dir: Path) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return script_dir / p


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    model_path = _resolve_model_path(Path(args.model))

    server_template_path = _resolve_template_path(args.server_template, script_dir)
    if not server_template_path.exists():
        raise FileNotFoundError(f"Server template not found: {server_template_path}")
    server_code = server_template_path.read_text(encoding="utf-8")

    telemetry_dashboard_template_path = _resolve_template_path(args.telemetry_dashboard_template, script_dir)
    if not telemetry_dashboard_template_path.exists():
        raise FileNotFoundError(f"Telemetry dashboard template not found: {telemetry_dashboard_template_path}")
    telemetry_dashboard_code = telemetry_dashboard_template_path.read_text(encoding="utf-8")

    predict_web_template_path = _resolve_template_path(args.predict_web_template, script_dir)
    if not predict_web_template_path.exists():
        raise FileNotFoundError(f"Predict web template not found: {predict_web_template_path}")
    predict_web_code = predict_web_template_path.read_text(encoding="utf-8")

    history_web_template_path = _resolve_template_path(args.history_web_template, script_dir)
    if not history_web_template_path.exists():
        raise FileNotFoundError(f"History web template not found: {history_web_template_path}")
    history_web_code = history_web_template_path.read_text(encoding="utf-8")

    context_dir = Path(args.context_dir)
    if context_dir.exists():
        shutil.rmtree(context_dir)

    _write_text(context_dir / "server.py", server_code)
    _write_text(context_dir / "telemetry_dashboard.html", telemetry_dashboard_code)
    _write_text(context_dir / "local_web_client.html", predict_web_code)
    _write_text(context_dir / "history_records.html", history_web_code)
    _write_text(context_dir / "Dockerfile", DOCKERFILE_CODE)
    _write_text(context_dir / "requirements.txt", REQUIREMENTS_CODE)
    (context_dir / "model").mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, context_dir / "model" / "best.pt")

    print(f"[ok] Docker context generated at: {context_dir.resolve()}")
    print(f"[ok] Model copied from: {model_path.resolve()}")
    print(f"[ok] server.py template: {server_template_path.resolve()}")
    print(f"[ok] telemetry dashboard template: {telemetry_dashboard_template_path.resolve()}")
    print(f"[ok] predict web template: {predict_web_template_path.resolve()}")
    print(f"[ok] history web template: {history_web_template_path.resolve()}")

    if not args.build:
        print("[skip] Docker build disabled.")
        return

    cmd = [
        "docker",
        "build",
        "--platform",
        args.platform,
        "-t",
        args.image_tag,
        str(context_dir),
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] Docker image built: {args.image_tag}")


if __name__ == "__main__":
    main()
