"""Assemble Docker build context for the API container and optionally build image.

This script copies validated templates/artifacts into an isolated context folder
so deployment can run from one deterministic directory.
"""

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
COPY decision_dashboard.html /app/decision_dashboard.html
COPY forecast_dashboard.html /app/forecast_dashboard.html
COPY demo_recording_dashboard.html /app/demo_recording_dashboard.html
COPY model /app/model

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
scikit-learn==1.5.2
"""


def parse_args() -> argparse.Namespace:
    """Parse packaging/build options for container context generation."""

    parser = argparse.ArgumentParser(
        description="Create Docker context for YOLO26 inference (with IoT telemetry) and optionally build image.",
    )
    parser.add_argument(
        "--model",
        default="apps/api/container/model/best.pt",
        help="Path to trained model checkpoint (.pt).",
    )
    parser.add_argument(
        "--context-dir",
        default="build/container_context",
        help="Output directory for Docker build context.",
    )
    parser.add_argument(
        "--server-template",
        default="apps/api/container/server.py",
        help="Template server.py path to copy into build context.",
    )
    parser.add_argument(
        "--telemetry-dashboard-template",
        default="apps/web/web_pages/telemetry_dashboard.html",
        help="Template telemetry dashboard HTML path to copy into build context.",
    )
    parser.add_argument(
        "--predict-web-template",
        default="apps/web/web_pages/local_web_client.html",
        help="Template predict web client HTML path to copy into build context.",
    )
    parser.add_argument(
        "--history-web-template",
        default="apps/web/web_pages/history_records.html",
        help="Template history records HTML path to copy into build context.",
    )
    parser.add_argument(
        "--decision-web-template",
        default="apps/web/web_pages/decision_dashboard.html",
        help="Template decision dashboard HTML path to copy into build context.",
    )
    parser.add_argument(
        "--forecast-web-template",
        default="apps/web/web_pages/forecast_dashboard.html",
        help="Template forecast dashboard HTML path to copy into build context.",
    )
    parser.add_argument(
        "--demo-web-template",
        default="apps/web/web_pages/demo_recording_dashboard.html",
        help="Template recording demo dashboard HTML path to copy into build context.",
    )
    parser.add_argument(
        "--model-dir",
        default="apps/api/container/model",
        help="Directory with model artifacts to copy into context (best.pt and optional demo artifacts).",
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
    """Create parent dirs and write UTF-8 text file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_model_path(model_path: Path) -> Path:
    """Resolve model file path, falling back to latest `runs/**/weights/best.pt`."""

    if model_path.exists():
        return model_path

    cwd = Path.cwd()
    candidates = sorted(cwd.glob("runs/**/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Model not found: {model_path}")


def _resolve_template_path(path_str: str, script_dir: Path, repo_root: Path) -> Path:
    """Resolve a template path across absolute path, CWD, repo-root, and script-dir."""

    p = Path(path_str)
    if p.is_absolute():
        return p
    if p.exists():
        return p
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    return script_dir / p


def main() -> None:
    """Generate container build context and optionally run docker build."""

    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    model_path = _resolve_model_path(Path(args.model))
    model_dir = _resolve_template_path(args.model_dir, script_dir, repo_root)
    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    server_template_path = _resolve_template_path(args.server_template, script_dir, repo_root)
    if not server_template_path.exists():
        raise FileNotFoundError(f"Server template not found: {server_template_path}")
    server_code = server_template_path.read_text(encoding="utf-8")

    telemetry_dashboard_template_path = _resolve_template_path(args.telemetry_dashboard_template, script_dir, repo_root)
    if not telemetry_dashboard_template_path.exists():
        raise FileNotFoundError(f"Telemetry dashboard template not found: {telemetry_dashboard_template_path}")
    telemetry_dashboard_code = telemetry_dashboard_template_path.read_text(encoding="utf-8")

    predict_web_template_path = _resolve_template_path(args.predict_web_template, script_dir, repo_root)
    if not predict_web_template_path.exists():
        raise FileNotFoundError(f"Predict web template not found: {predict_web_template_path}")
    predict_web_code = predict_web_template_path.read_text(encoding="utf-8")

    history_web_template_path = _resolve_template_path(args.history_web_template, script_dir, repo_root)
    if not history_web_template_path.exists():
        raise FileNotFoundError(f"History web template not found: {history_web_template_path}")
    history_web_code = history_web_template_path.read_text(encoding="utf-8")

    decision_web_template_path = _resolve_template_path(args.decision_web_template, script_dir, repo_root)
    if not decision_web_template_path.exists():
        raise FileNotFoundError(f"Decision web template not found: {decision_web_template_path}")
    decision_web_code = decision_web_template_path.read_text(encoding="utf-8")

    forecast_web_template_path = _resolve_template_path(args.forecast_web_template, script_dir, repo_root)
    if not forecast_web_template_path.exists():
        raise FileNotFoundError(f"Forecast web template not found: {forecast_web_template_path}")
    forecast_web_code = forecast_web_template_path.read_text(encoding="utf-8")

    demo_web_template_path = _resolve_template_path(args.demo_web_template, script_dir, repo_root)
    if not demo_web_template_path.exists():
        raise FileNotFoundError(f"Demo web template not found: {demo_web_template_path}")
    demo_web_code = demo_web_template_path.read_text(encoding="utf-8")

    context_dir = Path(args.context_dir)
    # Recreate context from scratch to avoid stale deployment artifacts.
    if context_dir.exists():
        shutil.rmtree(context_dir)

    _write_text(context_dir / "server.py", server_code)
    _write_text(context_dir / "telemetry_dashboard.html", telemetry_dashboard_code)
    _write_text(context_dir / "local_web_client.html", predict_web_code)
    _write_text(context_dir / "history_records.html", history_web_code)
    _write_text(context_dir / "decision_dashboard.html", decision_web_code)
    _write_text(context_dir / "forecast_dashboard.html", forecast_web_code)
    _write_text(context_dir / "demo_recording_dashboard.html", demo_web_code)
    _write_text(context_dir / "Dockerfile", DOCKERFILE_CODE)
    _write_text(context_dir / "requirements.txt", REQUIREMENTS_CODE)
    shutil.copytree(model_dir, context_dir / "model", dirs_exist_ok=True)
    if not (context_dir / "model" / "best.pt").exists():
        shutil.copy2(model_path, context_dir / "model" / "best.pt")

    print(f"[ok] Docker context generated at: {context_dir.resolve()}")
    print(f"[ok] Model copied from: {model_path.resolve()}")
    print(f"[ok] Model directory copied from: {model_dir.resolve()}")
    print(f"[ok] server.py template: {server_template_path.resolve()}")
    print(f"[ok] telemetry dashboard template: {telemetry_dashboard_template_path.resolve()}")
    print(f"[ok] predict web template: {predict_web_template_path.resolve()}")
    print(f"[ok] history web template: {history_web_template_path.resolve()}")
    print(f"[ok] decision web template: {decision_web_template_path.resolve()}")
    print(f"[ok] forecast web template: {forecast_web_template_path.resolve()}")
    print(f"[ok] demo web template: {demo_web_template_path.resolve()}")

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
