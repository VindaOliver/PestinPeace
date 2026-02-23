from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, File, HTTPException, Header, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from ultralytics import YOLO

MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/best.pt")
DEFAULT_CONF = float(os.getenv("DEFAULT_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("DEFAULT_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("DEFAULT_IMGSZ", "640"))
DEFAULT_MAX_DET = int(os.getenv("DEFAULT_MAX_DET", "1000"))

BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_IMAGES = os.getenv("BLOB_CONTAINER_IMAGES", "aphid-images")
BLOB_CONTAINER_HISTORY = os.getenv("BLOB_CONTAINER_HISTORY", "aphid-history")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", BLOB_CONNECTION_STRING)
TELEMETRY_TABLE = os.getenv("TELEMETRY_TABLE", "iottelemetry")
IOT_API_KEY = os.getenv("IOT_API_KEY", "")
TELEMETRY_DASHBOARD_PATH = "/app/telemetry_dashboard.html"
PREDICT_DASHBOARD_PATH = "/app/local_web_client.html"
HISTORY_DASHBOARD_PATH = "/app/history_records.html"

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

model = YOLO(MODEL_PATH)
app = FastAPI(title="Aphid YOLO26 Inference API", version="1.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

blob_service: BlobServiceClient | None = None
blob_init_error = ""
blob_image_error = ""
blob_history_error = ""
if BLOB_CONNECTION_STRING:
    try:
        blob_service = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
    except Exception as exc:
        blob_init_error = str(exc)
        blob_service = None

if blob_service is not None:
    try:
        blob_service.get_container_client(BLOB_CONTAINER_IMAGES).create_container()
    except Exception:
        pass
    try:
        blob_service.get_container_client(BLOB_CONTAINER_IMAGES).get_container_properties()
    except Exception as exc:
        blob_image_error = str(exc)

    try:
        blob_service.get_container_client(BLOB_CONTAINER_HISTORY).create_container()
    except Exception:
        pass
    try:
        blob_service.get_container_client(BLOB_CONTAINER_HISTORY).get_container_properties()
    except Exception as exc:
        blob_history_error = str(exc)

table_service: TableServiceClient | None = None
telemetry_table = None
telemetry_init_error = ""
if AZURE_STORAGE_CONNECTION_STRING:
    try:
        table_service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        table_service.create_table_if_not_exists(TELEMETRY_TABLE)
        telemetry_table = table_service.get_table_client(TELEMETRY_TABLE)
    except Exception as exc:
        telemetry_init_error = str(exc)
        telemetry_table = None
else:
    telemetry_init_error = "AZURE_STORAGE_CONNECTION_STRING is empty."


class TelemetryIn(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    temperature: float | None = None
    humidity: float | None = None
    light: float | None = None
    ts: datetime | None = None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return cleaned or "image.jpg"


def _upload_image_to_blob(blob_name: str, raw: bytes, content_type: str) -> str:
    if blob_service is None:
        raise RuntimeError("Blob service is not configured.")
    if blob_image_error:
        raise RuntimeError(f"Image blob container unavailable: {blob_image_error}")
    blob_client = blob_service.get_blob_client(container=BLOB_CONTAINER_IMAGES, blob=blob_name)
    blob_client.upload_blob(
        raw,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
    )
    return blob_client.url


def _upload_history_to_blob(blob_name: str, payload: dict[str, Any]) -> str:
    if blob_service is None:
        raise RuntimeError("Blob service is not configured.")
    if blob_history_error:
        raise RuntimeError(f"History blob container unavailable: {blob_history_error}")

    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    blob_client = blob_service.get_blob_client(container=BLOB_CONTAINER_HISTORY, blob=blob_name)
    blob_client.upload_blob(
        raw,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return blob_client.url


def _desc_row_key(ts: datetime) -> str:
    ms = int(ts.timestamp() * 1000)
    inv = 9999999999999 - ms
    return f"{inv:013d}_{uuid.uuid4().hex[:8]}"


def _check_iot_api_key(x_api_key: str | None) -> None:
    if not IOT_API_KEY:
        return
    if x_api_key != IOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_path": MODEL_PATH,
        "blob_enabled": blob_service is not None,
        "blob_init_error": blob_init_error or None,
        "blob_image_container": BLOB_CONTAINER_IMAGES,
        "blob_image_error": blob_image_error or None,
        "history_enabled": blob_service is not None and not blob_history_error,
        "history_container": BLOB_CONTAINER_HISTORY,
        "history_error": blob_history_error or None,
        "telemetry_enabled": telemetry_table is not None,
        "telemetry_init_error": telemetry_init_error or None,
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
    if blob_service is not None and not blob_image_error:
        try:
            image_url = _upload_image_to_blob(image_blob_name, raw, image.content_type or "image/jpeg")
        except Exception as exc:
            storage_error = str(exc)
    else:
        storage_error = blob_image_error or "Blob storage is not configured."

    history_blob_name = f"{request_id}.json"
    history_url = None
    history_error = None
    history_payload: dict[str, Any] = {
        "request_id": request_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "filename": image.filename,
        "count": len(detections),
        "detections": detections,
        "query": {
            "conf": float(conf),
            "iou": float(iou),
            "imgsz": int(imgsz),
            "max_det": int(max_det),
        },
        "image_blob_name": image_blob_name if image_url else None,
        "image_blob_url": image_url,
        "blob_saved": storage_error is None,
    }
    if storage_error:
        history_payload["storage_error"] = storage_error

    if blob_service is not None and not blob_history_error:
        try:
            history_url = _upload_history_to_blob(history_blob_name, history_payload)
        except Exception as exc:
            history_error = str(exc)
    else:
        history_error = blob_history_error or "History blob storage is not configured."

    response = {
        "request_id": request_id,
        "filename": image.filename,
        "count": len(detections),
        "detections": detections,
        "blob_saved": storage_error is None,
        "history_saved": history_error is None,
    }
    if image_url:
        response["image_blob_name"] = image_blob_name
        response["image_blob_url"] = image_url
    if storage_error:
        response["storage_error"] = storage_error
    if history_url:
        response["history_blob_name"] = history_blob_name
        response["history_blob_url"] = history_url
    if history_error:
        response["history_error"] = history_error
    return response


@app.get("/history")
def get_history(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    if blob_service is None:
        raise HTTPException(status_code=503, detail="Blob storage is not configured.")
    if blob_history_error:
        raise HTTPException(status_code=503, detail=f"History container unavailable: {blob_history_error}")

    container_client = blob_service.get_container_client(BLOB_CONTAINER_HISTORY)
    blobs = list(container_client.list_blobs())
    blobs.sort(key=lambda b: b.name, reverse=True)

    records: list[dict[str, Any]] = []
    for b in blobs[:limit]:
        blob_client = blob_service.get_blob_client(container=BLOB_CONTAINER_HISTORY, blob=b.name)
        try:
            content = blob_client.download_blob().readall()
            payload = json.loads(content)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        payload.setdefault("history_blob_name", b.name)
        payload.setdefault("history_blob_url", blob_client.url)
        if getattr(b, "last_modified", None):
            payload.setdefault("history_last_modified_utc", b.last_modified.isoformat())
        records.append(payload)

    return {
        "count": len(records),
        "limit": limit,
        "container": BLOB_CONTAINER_HISTORY,
        "records": records,
    }


@app.post("/telemetry")
def upload_telemetry(
    payload: TelemetryIn,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _check_iot_api_key(x_api_key)

    if telemetry_table is None:
        raise HTTPException(status_code=503, detail=f"Telemetry storage unavailable: {telemetry_init_error}")

    ts = payload.ts.astimezone(timezone.utc) if payload.ts else datetime.now(timezone.utc)
    entity = {
        "PartitionKey": payload.device_id,
        "RowKey": _desc_row_key(ts),
        "device_id": payload.device_id,
        "ts": ts.isoformat(),
        "temperature": payload.temperature,
        "humidity": payload.humidity,
        "light": payload.light,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    telemetry_table.upsert_entity(entity=entity)
    return {"status": "ok", "device_id": payload.device_id, "ts": entity["ts"]}


@app.get("/telemetry/latest")
def telemetry_latest(
    device_id: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _check_iot_api_key(x_api_key)

    if telemetry_table is None:
        raise HTTPException(status_code=503, detail=f"Telemetry storage unavailable: {telemetry_init_error}")

    items: list[dict[str, Any]] = []
    query_filter = "PartitionKey eq @device_id"
    parameters = {"device_id": device_id}

    for entity in telemetry_table.query_entities(query_filter=query_filter, parameters=parameters):
        items.append(
            {
                "device_id": entity.get("device_id"),
                "ts": entity.get("ts"),
                "temperature": entity.get("temperature"),
                "humidity": entity.get("humidity"),
                "light": entity.get("light"),
            }
        )
        if len(items) >= limit:
            break

    return {"device_id": device_id, "count": len(items), "items": items}


@app.get("/telemetry/dashboard")
def telemetry_dashboard() -> FileResponse:
    if not os.path.exists(TELEMETRY_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(TELEMETRY_DASHBOARD_PATH)


@app.get("/predict/dashboard")
def predict_dashboard() -> FileResponse:
    if not os.path.exists(PREDICT_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(PREDICT_DASHBOARD_PATH)


@app.get("/history/dashboard")
def history_dashboard() -> FileResponse:
    if not os.path.exists(HISTORY_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(HISTORY_DASHBOARD_PATH)
