"""Main FastAPI service for image inference, telemetry, history, and weekly spray decision demo.

This module wires together:
1) YOLO image inference endpoint (`/predict`)
2) Telemetry ingest/query endpoints (`/telemetry`, `/telemetry/latest`)
3) History retrieval endpoint (`/history`)
4) Weekly spray-scope decision endpoint (`/decision/weekly`)
5) Built-in dashboard static page routes
"""

from __future__ import annotations

import io
import json
import math
import os
import pickle
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, File, HTTPException, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field
from ultralytics import YOLO

# -----------------------------
# Runtime configuration
# -----------------------------
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/best.pt")
DEFAULT_CONF = float(os.getenv("DEFAULT_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("DEFAULT_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("DEFAULT_IMGSZ", "640"))
DEFAULT_MAX_DET = int(os.getenv("DEFAULT_MAX_DET", "1000"))
TEPP_DEMO_MODEL_PATH = os.getenv("TEPP_DEMO_MODEL_PATH", "/app/model/tepp_demo_scope_model.pkl")
TEPP_DEMO_META_PATH = os.getenv("TEPP_DEMO_META_PATH", "/app/model/tepp_demo_meta.json")
TEPP_DEFAULT_RATE_KG_HA = float(os.getenv("TEPP_DEFAULT_RATE_KG_HA", "0.14"))

BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_IMAGES = os.getenv("BLOB_CONTAINER_IMAGES", "aphid-images")
BLOB_CONTAINER_HISTORY = os.getenv("BLOB_CONTAINER_HISTORY", "aphid-history")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", BLOB_CONNECTION_STRING)
TELEMETRY_TABLE = os.getenv("TELEMETRY_TABLE", "iottelemetry")
IOT_API_KEY = os.getenv("IOT_API_KEY", "")
TELEMETRY_DASHBOARD_PATH = "/app/telemetry_dashboard.html"
PREDICT_DASHBOARD_PATH = "/app/local_web_client.html"
HISTORY_DASHBOARD_PATH = "/app/history_records.html"
DECISION_DASHBOARD_PATH = "/app/decision_dashboard.html"

# Fail fast if the primary YOLO model is not available.
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

model = YOLO(MODEL_PATH)
app = FastAPI(title="Aphid YOLO26 Inference API", version="1.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# -----------------------------
# Azure Blob clients (images/history)
# -----------------------------
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

# Validate/create containers so runtime errors are explicit in /health.
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

# -----------------------------
# Azure Table client (telemetry)
# -----------------------------
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
    """Payload schema for telemetry upload."""

    device_id: str = Field(..., min_length=1, max_length=64)
    temperature: float | None = None
    humidity: float | None = None
    pressure_hpa: float | None = None
    light: float | None = None
    ts: datetime | None = None


class WeeklyScopeDecisionIn(BaseModel):
    """Payload schema for weekly spray-scope decision inference."""

    aphid_count: int = Field(..., ge=0)
    field_area_ha: float = Field(..., gt=0)
    exposure_days: int = Field(default=7, ge=1, le=14)
    week_start: date | None = None
    prev_catch_rate: float | None = Field(default=None, ge=0)
    catch_trend: float | None = None
    t_mean: float = 15.0
    rh_mean: float = Field(default=70.0, ge=0, le=100)
    vpd_mean: float | None = Field(default=None, ge=0)
    in_tepp_window: int | None = Field(default=None, ge=0, le=1)
    apps_so_far: int = Field(default=0, ge=0, le=20)
    respect_compliance_gate: bool = True


tepp_model = None
tepp_model_error = ""
tepp_meta: dict[str, Any] = {}
tepp_feature_cols: list[str] = [
    "log_catch",
    "catch_trend",
    "T_mean",
    "RH_mean",
    "VPD_mean",
    "doy_sin",
    "doy_cos",
    "in_tepp_window",
    "apps_so_far",
]
tepp_teacher_q50 = 0.5
tepp_teacher_q85 = 2.0
tepp_treated_fraction_by_scope = {0: 0.0, 1: 0.3, 2: 1.0}
tepp_water_by_scope = {0: 0, 1: 350, 2: 500}
tepp_rate_kg_ha = TEPP_DEFAULT_RATE_KG_HA


def _load_json_file(path: str) -> dict[str, Any]:
    """Load a JSON object from disk; return empty dict for non-object JSON."""

    with open(path, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    return parsed if isinstance(parsed, dict) else {}


def _normalize_scope_float_map(raw: Any, defaults: dict[int, float]) -> dict[int, float]:
    """Normalize meta scope map keys to int and values to float, with defaults."""

    merged = dict(defaults)
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        try:
            merged[int(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return merged


def _normalize_scope_int_map(raw: Any, defaults: dict[int, int]) -> dict[int, int]:
    """Normalize meta scope map keys/values to int, with defaults."""

    merged = dict(defaults)
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        try:
            merged[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return merged


def _init_tepp_demo_assets() -> None:
    """Load decision model and meta from disk into module-level runtime globals."""

    global tepp_model, tepp_model_error, tepp_meta
    global tepp_feature_cols, tepp_teacher_q50, tepp_teacher_q85
    global tepp_treated_fraction_by_scope, tepp_water_by_scope, tepp_rate_kg_ha

    tepp_model = None
    tepp_model_error = ""
    tepp_meta = {}

    if os.path.exists(TEPP_DEMO_META_PATH):
        try:
            tepp_meta = _load_json_file(TEPP_DEMO_META_PATH)
            feature_cols = tepp_meta.get("feature_cols")
            if isinstance(feature_cols, list) and all(isinstance(c, str) for c in feature_cols):
                tepp_feature_cols = feature_cols
            teacher_quantiles = tepp_meta.get("teacher_quantiles", {})
            if isinstance(teacher_quantiles, dict):
                tepp_teacher_q50 = float(teacher_quantiles.get("q50", tepp_teacher_q50))
                tepp_teacher_q85 = float(teacher_quantiles.get("q85", tepp_teacher_q85))
            tepp_treated_fraction_by_scope = _normalize_scope_float_map(
                tepp_meta.get("treated_fraction_by_scope"),
                tepp_treated_fraction_by_scope,
            )
            tepp_water_by_scope = _normalize_scope_int_map(
                tepp_meta.get("water_by_scope_L_ha"),
                tepp_water_by_scope,
            )
            tepp_rate_kg_ha = float(tepp_meta.get("tepp_rate_kg_ha", tepp_rate_kg_ha))
        except Exception as exc:
            tepp_model_error = f"Meta load failed: {exc}"

    if not os.path.exists(TEPP_DEMO_MODEL_PATH):
        if not tepp_model_error:
            tepp_model_error = f"Decision model not found: {TEPP_DEMO_MODEL_PATH}"
        return

    try:
        with open(TEPP_DEMO_MODEL_PATH, "rb") as f:
            tepp_model = pickle.load(f)
    except Exception as exc:
        tepp_model = None
        if tepp_model_error:
            tepp_model_error = f"{tepp_model_error}; model load failed: {exc}"
        else:
            tepp_model_error = f"Model load failed: {exc}"


_init_tepp_demo_assets()


def _utc_stamp() -> str:
    """UTC timestamp used in request IDs and blob naming."""

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_filename(name: str) -> str:
    """Keep only safe filename characters for blob/object storage."""

    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return cleaned or "image.jpg"


def _upload_image_to_blob(blob_name: str, raw: bytes, content_type: str) -> str:
    """Upload original request image to image blob container and return public URL."""

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
    """Upload request/response trace JSON to history blob container and return URL."""

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


def _extract_blob_name_from_url(blob_url: str, container: str) -> str | None:
    """Extract blob name from a canonical Blob URL under a known container."""

    if not blob_url:
        return None
    parsed = urlparse(blob_url)
    path = (parsed.path or "").lstrip("/")
    prefix = f"{container}/"
    if not path.startswith(prefix):
        return None
    name = path[len(prefix) :]
    return name or None


def _build_blob_view_url(request: Request, route_prefix: str, blob_name: str) -> str:
    """Build absolute API URL for proxied blob viewing/download."""

    cleaned = blob_name.lstrip("/")
    encoded = quote(cleaned, safe="")
    base = str(request.base_url).rstrip("/")
    return f"{base}{route_prefix}/{encoded}"


def _download_blob_bytes(container: str, blob_name: str) -> tuple[bytes, str]:
    """Read blob bytes + content type from a private container via server identity/conn string."""

    if blob_service is None:
        raise HTTPException(status_code=503, detail="Blob storage is not configured.")
    if container == BLOB_CONTAINER_IMAGES and blob_image_error:
        raise HTTPException(status_code=503, detail=f"Image container unavailable: {blob_image_error}")
    if container == BLOB_CONTAINER_HISTORY and blob_history_error:
        raise HTTPException(status_code=503, detail=f"History container unavailable: {blob_history_error}")

    cleaned = blob_name.lstrip("/")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Blob name is required.")

    blob_client = blob_service.get_blob_client(container=container, blob=cleaned)
    try:
        payload = blob_client.download_blob().readall()
        props = blob_client.get_blob_properties()
    except Exception as exc:
        msg = str(exc)
        if "BlobNotFound" in msg or "ResourceNotFound" in msg:
            raise HTTPException(status_code=404, detail="Blob not found.") from exc
        raise HTTPException(status_code=502, detail=f"Blob read failed: {exc}") from exc

    content_type = "application/octet-stream"
    try:
        content_type = props.content_settings.content_type or content_type
    except Exception:
        pass
    return payload, content_type


def _desc_row_key(ts: datetime) -> str:
    """Create reverse-time row key so latest telemetry appears first when scanning."""

    ms = int(ts.timestamp() * 1000)
    inv = 9999999999999 - ms
    return f"{inv:013d}_{uuid.uuid4().hex[:8]}"


def _check_iot_api_key(x_api_key: str | None) -> None:
    """Validate optional API key gate for telemetry endpoints."""

    if not IOT_API_KEY:
        return
    if x_api_key != IOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")


def _vpd_kpa(t_c: float, rh_pct: float) -> float:
    """Compute VPD (kPa) from temperature and relative humidity."""

    es = 0.6108 * math.exp((17.27 * t_c) / (t_c + 237.3))
    ea = es * (rh_pct / 100.0)
    return max(es - ea, 0.0)


def _resolve_doy(week_start: date | None) -> int:
    """Resolve day-of-year from payload week_start (or current UTC date)."""

    d = week_start if week_start is not None else datetime.now(timezone.utc).date()
    return d.timetuple().tm_yday


def _resolve_tepp_window(week_start_doy: int, in_tepp_window: int | None) -> int:
    """Resolve application window flag from explicit input or demo DOY fallback rule."""

    if in_tepp_window is not None:
        return 1 if int(in_tepp_window) == 1 else 0
    return 1 if 135 <= week_start_doy <= 260 else 0


def _build_tepp_feature_map(payload: WeeklyScopeDecisionIn) -> dict[str, float]:
    """Transform request payload into model-ready decision features."""

    catch_rate = float(payload.aphid_count) / float(payload.exposure_days)
    catch_trend = (
        float(payload.catch_trend)
        if payload.catch_trend is not None
        else (catch_rate - float(payload.prev_catch_rate) if payload.prev_catch_rate is not None else 0.0)
    )
    doy = _resolve_doy(payload.week_start)
    in_tepp_window = _resolve_tepp_window(doy, payload.in_tepp_window)
    vpd = float(payload.vpd_mean) if payload.vpd_mean is not None else _vpd_kpa(float(payload.t_mean), float(payload.rh_mean))

    return {
        "catch_rate": catch_rate,
        "log_catch": math.log1p(catch_rate),
        "catch_trend": catch_trend,
        "T_mean": float(payload.t_mean),
        "RH_mean": float(payload.rh_mean),
        "VPD_mean": float(vpd),
        "doy_sin": math.sin(2.0 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2.0 * math.pi * doy / 365.25),
        "in_tepp_window": float(in_tepp_window),
        "apps_so_far": float(payload.apps_so_far),
        "doy": float(doy),
    }


def _scope_name(scope_class: int) -> str:
    """Map scope class index to API-facing semantic name."""

    if scope_class == 1:
        return "boundary_band"
    if scope_class == 2:
        return "full_field"
    return "no_spray"


def _tepp_model_proba_map(features: list[float]) -> dict[str, float] | None:
    """Return class probability map if model supports predict_proba."""

    if tepp_model is None or not hasattr(tepp_model, "predict_proba"):
        return None
    try:
        proba = tepp_model.predict_proba([features])[0]
    except Exception:
        return None

    classes_raw = getattr(tepp_model, "classes_", None)
    if classes_raw is None and hasattr(tepp_model, "named_steps"):
        clf = tepp_model.named_steps.get("clf")
        if clf is not None:
            classes_raw = getattr(clf, "classes_", None)
    if classes_raw is None:
        return None

    class_probs: dict[str, float] = {}
    for idx, c in enumerate(classes_raw):
        if idx >= len(proba):
            continue
        class_probs[str(int(c))] = float(proba[idx])
    return class_probs


def _infer_scope_by_model(features: list[float]) -> int | None:
    """Infer scope class from loaded model; return None on runtime/model errors."""

    if tepp_model is None:
        return None
    try:
        predicted = tepp_model.predict([features])[0]
        return int(predicted)
    except Exception:
        return None


def _infer_scope_by_teacher_rule(feature_map: dict[str, float]) -> int:
    """Fallback weak-supervision rule used when model is unavailable."""

    catch_rate = feature_map["catch_rate"]
    scope_class = 0
    if catch_rate >= tepp_teacher_q85:
        scope_class = 2
    elif catch_rate >= tepp_teacher_q50:
        scope_class = 1

    if scope_class == 1 and feature_map["catch_trend"] > 0.8 and feature_map["T_mean"] > 14:
        scope_class = 2
    return scope_class


@app.get("/health")
def health() -> dict[str, Any]:
    """Service and dependency health summary endpoint."""

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
        "tepp_demo_model_enabled": tepp_model is not None,
        "tepp_demo_model_path": TEPP_DEMO_MODEL_PATH,
        "tepp_demo_meta_path": TEPP_DEMO_META_PATH,
        "tepp_demo_model_error": tepp_model_error or None,
    }


@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    conf: float = DEFAULT_CONF,
    iou: float = DEFAULT_IOU,
    imgsz: int = DEFAULT_IMGSZ,
    max_det: int = DEFAULT_MAX_DET,
) -> dict[str, Any]:
    """Run YOLO inference on uploaded image and optionally persist blobs/history."""

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
def get_history(request: Request, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """List recent inference history JSON records from blob storage."""

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
        payload.setdefault("history_view_url", _build_blob_view_url(request, "/history/blob", b.name))
        image_name = payload.get("image_blob_name")
        if not isinstance(image_name, str) or not image_name:
            image_url = payload.get("image_blob_url")
            if isinstance(image_url, str):
                image_name = _extract_blob_name_from_url(image_url, BLOB_CONTAINER_IMAGES)
        if isinstance(image_name, str) and image_name:
            payload.setdefault("image_blob_name", image_name)
            payload.setdefault("image_view_url", _build_blob_view_url(request, "/image/blob", image_name))
        if getattr(b, "last_modified", None):
            payload.setdefault("history_last_modified_utc", b.last_modified.isoformat())
        records.append(payload)

    return {
        "count": len(records),
        "limit": limit,
        "container": BLOB_CONTAINER_HISTORY,
        "records": records,
    }


@app.get("/history/blob/{blob_name:path}")
def history_blob_proxy(blob_name: str) -> Response:
    """Serve a history JSON blob through API so private storage doesn't need public access."""

    payload, content_type = _download_blob_bytes(BLOB_CONTAINER_HISTORY, blob_name)
    filename = os.path.basename(blob_name) or "history.json"
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/image/blob/{blob_name:path}")
def image_blob_proxy(blob_name: str) -> Response:
    """Serve an image blob through API so private storage doesn't need public access."""

    payload, content_type = _download_blob_bytes(BLOB_CONTAINER_IMAGES, blob_name)
    filename = os.path.basename(blob_name) or "image.bin"
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/telemetry")
def upload_telemetry(
    payload: TelemetryIn,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Upsert one telemetry sample into Azure Table Storage."""

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
        "pressure_hpa": payload.pressure_hpa,
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
    """Return latest telemetry rows for a device."""

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
                "pressure_hpa": entity.get("pressure_hpa"),
                "light": entity.get("light"),
            }
        )
        if len(items) >= limit:
            break

    return {"device_id": device_id, "count": len(items), "items": items}


@app.post("/decision/weekly")
def weekly_scope_decision(payload: WeeklyScopeDecisionIn) -> dict[str, Any]:
    """Return weekly spray-scope recommendation with compliance gate and dosage math."""

    feature_map = _build_tepp_feature_map(payload)
    feature_values = [float(feature_map.get(c, 0.0)) for c in tepp_feature_cols]

    predicted_scope = _infer_scope_by_model(feature_values)
    model_source = "tepp_demo_scope_model"
    class_probabilities = _tepp_model_proba_map(feature_values)
    if predicted_scope is None:
        predicted_scope = _infer_scope_by_teacher_rule(feature_map)
        model_source = "teacher_rule_fallback"
        class_probabilities = None

    scope_before_gate = int(predicted_scope)
    gate_applied = False
    gate_reason = None
    in_tepp_window = int(feature_map["in_tepp_window"])

    if payload.respect_compliance_gate:
        if in_tepp_window != 1:
            predicted_scope = 0
            gate_applied = True
            gate_reason = "Outside Teppeki application window."
        elif payload.apps_so_far >= 1:
            predicted_scope = 0
            gate_applied = True
            gate_reason = "Maximum application count reached (>= 1)."

    scope_class = int(max(0, min(2, predicted_scope)))
    treated_fraction = float(tepp_treated_fraction_by_scope.get(scope_class, 0.0))
    water_l_ha = int(tepp_water_by_scope.get(scope_class, 0))
    product_kg = float(tepp_rate_kg_ha * payload.field_area_ha * treated_fraction)
    spray_l = float(water_l_ha * payload.field_area_ha * treated_fraction)

    response: dict[str, Any] = {
        "scope_class": scope_class,
        "scope_name": _scope_name(scope_class),
        "treated_fraction": treated_fraction,
        "water_l_ha": water_l_ha,
        "product_kg": round(product_kg, 4),
        "spray_l": round(spray_l, 2),
        "inputs": {
            "aphid_count": payload.aphid_count,
            "field_area_ha": payload.field_area_ha,
            "exposure_days": payload.exposure_days,
            "catch_rate": round(feature_map["catch_rate"], 4),
            "catch_trend": round(feature_map["catch_trend"], 4),
            "t_mean": round(feature_map["T_mean"], 3),
            "rh_mean": round(feature_map["RH_mean"], 3),
            "vpd_mean": round(feature_map["VPD_mean"], 4),
            "week_start_doy": int(feature_map["doy"]),
            "in_tepp_window": in_tepp_window,
            "apps_so_far": payload.apps_so_far,
        },
        "compliance": {
            "respect_compliance_gate": payload.respect_compliance_gate,
            "scope_before_gate": scope_before_gate,
            "gate_applied": gate_applied,
            "gate_reason": gate_reason,
            "max_apps_allowed": 1,
        },
        "model": {
            "source": model_source,
            "loaded": tepp_model is not None,
            "feature_cols": tepp_feature_cols,
            "teacher_quantiles": {"q50": tepp_teacher_q50, "q85": tepp_teacher_q85},
            "class_probabilities": class_probabilities,
            "error": tepp_model_error or None,
        },
        "label_constraints": {
            "tepp_rate_kg_ha": tepp_rate_kg_ha,
            "water_range_l_ha": [200, 500],
        },
    }
    return response


@app.get("/telemetry/dashboard")
def telemetry_dashboard() -> FileResponse:
    """Serve telemetry dashboard HTML bundled in container image."""

    if not os.path.exists(TELEMETRY_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(TELEMETRY_DASHBOARD_PATH)


@app.get("/predict/dashboard")
def predict_dashboard() -> FileResponse:
    """Serve predict dashboard HTML bundled in container image."""

    if not os.path.exists(PREDICT_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(PREDICT_DASHBOARD_PATH)


@app.get("/history/dashboard")
def history_dashboard() -> FileResponse:
    """Serve history dashboard HTML bundled in container image."""

    if not os.path.exists(HISTORY_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(HISTORY_DASHBOARD_PATH)


@app.get("/decision/dashboard")
def decision_dashboard() -> FileResponse:
    """Serve weekly decision dashboard HTML bundled in container image."""

    if not os.path.exists(DECISION_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(DECISION_DASHBOARD_PATH)
