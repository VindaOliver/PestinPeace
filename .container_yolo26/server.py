from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from jwt import InvalidTokenError, PyJWKClient
from PIL import Image
from ultralytics import YOLO

MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/best.pt")
DEFAULT_CONF = float(os.getenv("DEFAULT_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("DEFAULT_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("DEFAULT_IMGSZ", "640"))
DEFAULT_MAX_DET = int(os.getenv("DEFAULT_MAX_DET", "1000"))

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_IMAGES = os.getenv("BLOB_CONTAINER_IMAGES", "aphid-images")
BLOB_CONTAINER_HISTORY = os.getenv("BLOB_CONTAINER_HISTORY", "aphid-history")


def _parse_csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "").strip()
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "").strip()
ENTRA_AUDIENCE = os.getenv("ENTRA_AUDIENCE", "").strip()
ENTRA_ALLOWED_GROUP_IDS = _parse_csv_set(os.getenv("ENTRA_ALLOWED_GROUP_IDS", ""))
ENTRA_ALLOWED_USER_OBJECT_IDS = _parse_csv_set(os.getenv("ENTRA_ALLOWED_USER_OBJECT_IDS", ""))
ENTRA_ALLOWED_ROLES = _parse_csv_set(os.getenv("ENTRA_ALLOWED_ROLES", ""))
ENTRA_ENABLED = bool(ENTRA_TENANT_ID and ENTRA_CLIENT_ID)
ENTRA_ADMIN_POLICY_CONFIGURED = bool(
    ENTRA_ALLOWED_GROUP_IDS or ENTRA_ALLOWED_USER_OBJECT_IDS or ENTRA_ALLOWED_ROLES
)

if ENTRA_ENABLED:
    ENTRA_ISSUER = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0"
    ENTRA_AUDIENCES: list[str] = [ENTRA_CLIENT_ID, f"api://{ENTRA_CLIENT_ID}"]
    ENTRA_AUDIENCES.extend([x.strip() for x in ENTRA_AUDIENCE.split(",") if x.strip()])
    ENTRA_JWKS_URI = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"
    ENTRA_JWKS_CLIENT: PyJWKClient | None = PyJWKClient(ENTRA_JWKS_URI)
else:
    ENTRA_ISSUER = ""
    ENTRA_AUDIENCES = []
    ENTRA_JWKS_URI = ""
    ENTRA_JWKS_CLIENT = None

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
        blob_service.get_container_client(BLOB_CONTAINER_HISTORY).create_container()
    except Exception:
        pass
    try:
        blob_service.get_container_client(BLOB_CONTAINER_IMAGES).get_container_properties()
        blob_service.get_container_client(BLOB_CONTAINER_HISTORY).get_container_properties()
    except Exception as exc:
        blob_init_error = str(exc)
        blob_service = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return cleaned or "image.jpg"


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization must be Bearer token.")
    return parts[1].strip()


def _decode_entra_access_token(token: str) -> dict[str, Any]:
    if not ENTRA_ENABLED or ENTRA_JWKS_CLIENT is None:
        raise HTTPException(status_code=503, detail="Entra authentication is not configured.")

    try:
        signing_key = ENTRA_JWKS_CLIENT.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            audience=ENTRA_AUDIENCES,
            issuer=ENTRA_ISSUER,
        )
        return payload
    except InvalidTokenError as exc:
        raise HTTPException(status_code=403, detail=f"Invalid bearer token: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=403, detail=f"Token validation failed: {exc}") from exc


def _is_entra_admin(payload: dict[str, Any]) -> bool:
    if not ENTRA_ADMIN_POLICY_CONFIGURED:
        return False

    oid = str(payload.get("oid", "")).strip()
    if oid and oid in ENTRA_ALLOWED_USER_OBJECT_IDS:
        return True

    roles = payload.get("roles")
    if isinstance(roles, list):
        role_values = {str(x) for x in roles}
        if role_values & ENTRA_ALLOWED_ROLES:
            return True

    groups = payload.get("groups")
    if isinstance(groups, list):
        group_values = {str(x) for x in groups}
        if group_values & ENTRA_ALLOWED_GROUP_IDS:
            return True

    return False


def _require_admin(x_admin_token: str | None, authorization: str | None) -> None:
    if ENTRA_ENABLED:
        if not ENTRA_ADMIN_POLICY_CONFIGURED:
            raise HTTPException(
                status_code=503,
                detail="Entra admin allow list is not configured.",
            )
        token = _extract_bearer_token(authorization)
        payload = _decode_entra_access_token(token)
        if not _is_entra_admin(payload):
            raise HTTPException(status_code=403, detail="Forbidden.")
        return

    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured.")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden.")


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


def _upload_history_json(blob_name: str, payload: dict[str, Any]) -> str:
    if blob_service is None:
        raise RuntimeError("Blob service is not configured.")
    blob_client = blob_service.get_blob_client(container=BLOB_CONTAINER_HISTORY, blob=blob_name)
    blob_client.upload_blob(
        json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return blob_client.url


@app.get("/health")
def health() -> dict[str, Any]:
    auth_mode = "entra" if ENTRA_ENABLED else ("token" if bool(ADMIN_TOKEN) else "disabled")
    return {
        "status": "ok",
        "model_path": MODEL_PATH,
        "blob_enabled": blob_service is not None,
        "blob_init_error": blob_init_error or None,
        "admin_enabled": bool(ADMIN_TOKEN) or ENTRA_ENABLED,
        "auth_mode": auth_mode,
        "entra_enabled": ENTRA_ENABLED,
        "entra_admin_policy_configured": ENTRA_ADMIN_POLICY_CONFIGURED,
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
    history_blob_name = f"{request_id}.json"

    record = {
        "request_id": request_id,
        "timestamp_utc": _utc_now_iso(),
        "filename": image.filename,
        "count": len(detections),
        "detections": detections,
        "params": {
            "conf": float(conf),
            "iou": float(iou),
            "imgsz": int(imgsz),
            "max_det": int(max_det),
        },
        "model_path": MODEL_PATH,
    }

    storage_error = None
    if blob_service is not None:
        try:
            image_url = _upload_image_to_blob(image_blob_name, raw, image.content_type or "image/jpeg")
            record["image_blob_name"] = image_blob_name
            record["image_blob_url"] = image_url
            history_url = _upload_history_json(history_blob_name, record)
            record["history_blob_name"] = history_blob_name
            record["history_blob_url"] = history_url
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
    if storage_error:
        response["storage_error"] = storage_error
    return response


@app.get("/admin/history")
def admin_history(
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    _require_admin(x_admin_token, authorization)
    if blob_service is None:
        raise HTTPException(status_code=503, detail="Blob storage is not configured.")

    container = blob_service.get_container_client(BLOB_CONTAINER_HISTORY)
    blobs = sorted(container.list_blobs(), key=lambda b: b.name, reverse=True)

    records: list[dict[str, Any]] = []
    for blob in blobs[:limit]:
        try:
            payload = container.download_blob(blob.name).readall()
            records.append(json.loads(payload.decode("utf-8")))
        except Exception:
            records.append({"history_blob_name": blob.name, "error": "Failed to parse record."})

    return {
        "count": len(records),
        "limit": limit,
        "records": records,
    }
