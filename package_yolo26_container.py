from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


API_SERVER_CODE = r'''from __future__ import annotations

import io
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from ultralytics import YOLO

MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/best.pt")
DEFAULT_CONF = float(os.getenv("DEFAULT_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("DEFAULT_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("DEFAULT_IMGSZ", "640"))
DEFAULT_MAX_DET = int(os.getenv("DEFAULT_MAX_DET", "1000"))

BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_IMAGES = os.getenv("BLOB_CONTAINER_IMAGES", "aphid-images")

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

model = YOLO(MODEL_PATH)
app = FastAPI(title="Aphid YOLO26 Inference API", version="1.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

blob_service: BlobServiceClient | None = None
blob_init_error = ""
if BLOB_CONNECTION_STRING:
    try:
        blob_service = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        blob_service.get_container_client(BLOB_CONTAINER_IMAGES).create_container()
    except Exception:
        pass
    try:
        blob_service.get_container_client(BLOB_CONTAINER_IMAGES).get_container_properties()
    except Exception as exc:
        blob_init_error = str(exc)
        blob_service = None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return cleaned or "image.jpg"


def _upload_image_to_blob(blob_name: str, raw: bytes, content_type: str) -> str:
    if blob_service is None:
        raise RuntimeError("Blob service is not configured.")
    blob_client = blob_service.get_blob_client(container=BLOB_CONTAINER_IMAGES, blob=blob_name)
    blob_client.upload_blob(
        raw,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
    )
    return blob_client.url


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_path": MODEL_PATH,
        "blob_enabled": blob_service is not None,
        "blob_init_error": blob_init_error or None,
    }


@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    conf: float = DEFAULT_CONF,
    iou: float = DEFAULT_IOU,
    imgsz: int = DEFAULT_IMGSZ,
    max_det: int = DEFAULT_MAX_DET,
) -> dict[str, Any]:
    if not image.filename:
        raise HTTPException(status_code=400, detail="Missing image filename.")

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image.")

    try:
        pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc

    results = model.predict(
        source=pil_img,
        conf=float(conf),
        iou=float(iou),
        imgsz=int(imgsz),
        max_det=int(max_det),
        device="cpu",
        verbose=False,
    )

    r0 = results[0]
    boxes = r0.boxes
    names = r0.names
    detections: list[dict[str, Any]] = []

    if boxes is not None:
        xyxy = boxes.xyxy.detach().cpu().tolist() if boxes.xyxy is not None else []
        confs = boxes.conf.detach().cpu().tolist() if boxes.conf is not None else []
        clss = boxes.cls.detach().cpu().tolist() if boxes.cls is not None else []
        for i in range(len(xyxy)):
            cls_id = int(clss[i]) if i < len(clss) else -1
            detections.append(
                {
                    "class_id": cls_id,
                    "class_name": names.get(cls_id, str(cls_id)),
                    "confidence": float(confs[i]) if i < len(confs) else None,
                    "bbox_xyxy": [float(v) for v in xyxy[i]],
                }
            )

    request_id = f"{_utc_stamp()}_{uuid.uuid4().hex[:10]}"
    safe_name = _safe_filename(image.filename)
    image_blob_name = f"{request_id}_{safe_name}"
    storage_error = None
    image_url = None
    if blob_service is not None:
        try:
            image_url = _upload_image_to_blob(image_blob_name, raw, image.content_type or "image/jpeg")
        except Exception as exc:
            storage_error = str(exc)
    else:
        storage_error = "Blob storage is not configured."

    response = {
        "request_id": request_id,
        "filename": image.filename,
        "count": len(detections),
        "detections": detections,
        "blob_saved": storage_error is None,
    }
    if image_url:
        response["image_blob_name"] = image_blob_name
        response["image_blob_url"] = image_url
    if storage_error:
        response["storage_error"] = storage_error
    return response
'''


DOCKERFILE_CODE = """FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
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
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Docker context for YOLO26 inference and optionally build image.",
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
    path.write_text(text, encoding="ascii")


def _resolve_model_path(model_path: Path) -> Path:
    if model_path.exists():
        return model_path

    cwd = Path.cwd()
    candidates = sorted(cwd.glob("runs/**/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Model not found: {model_path}")


def main() -> None:
    args = parse_args()
    model_path = _resolve_model_path(Path(args.model))

    context_dir = Path(args.context_dir)
    if context_dir.exists():
        shutil.rmtree(context_dir)

    _write_text(context_dir / "server.py", API_SERVER_CODE)
    _write_text(context_dir / "Dockerfile", DOCKERFILE_CODE)
    _write_text(context_dir / "requirements.txt", REQUIREMENTS_CODE)
    (context_dir / "model").mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, context_dir / "model" / "best.pt")

    print(f"[ok] Docker context generated at: {context_dir.resolve()}")
    print(f"[ok] Model copied from: {model_path.resolve()}")

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
