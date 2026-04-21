"""Main FastAPI service for image inference, telemetry, history, and weekly spray decision demo.

This module wires together:
1) YOLO image inference endpoint (`/predict`)
2) Telemetry ingest/query endpoints (`/telemetry`, `/telemetry/latest`)
3) History retrieval endpoint (`/history`)
4) Weekly spray-scope decision endpoint (`/decision/weekly`)
5) Weekly aphid trend forecast endpoint (`/forecast/weekly`)
6) Grafana-friendly raw table query endpoints (`/grafana/telemetry`, `/grafana/aphidcounts`)
7) Built-in dashboard static page routes
"""

from __future__ import annotations

import io
import json
import math
import os
import pickle
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, File, HTTPException, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field
import requests
from ultralytics import YOLO

# -----------------------------
# Runtime configuration
# -----------------------------
APP_DIR = Path(__file__).resolve().parent
MODEL_PATH = os.getenv("MODEL_PATH", str(APP_DIR / "model" / "best.pt"))
DEFAULT_CONF = float(os.getenv("DEFAULT_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("DEFAULT_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("DEFAULT_IMGSZ", "640"))
DEFAULT_MAX_DET = int(os.getenv("DEFAULT_MAX_DET", "1000"))
TEPP_DEMO_MODEL_PATH = os.getenv("TEPP_DEMO_MODEL_PATH", str(APP_DIR / "model" / "tepp_demo_scope_model.pkl"))
TEPP_DEMO_META_PATH = os.getenv("TEPP_DEMO_META_PATH", str(APP_DIR / "model" / "tepp_demo_meta.json"))
TEPP_DEFAULT_RATE_KG_HA = float(os.getenv("TEPP_DEFAULT_RATE_KG_HA", "0.14"))
APHID_FORECAST_MODEL_PATH = os.getenv("APHID_FORECAST_MODEL_PATH", str(APP_DIR / "model" / "aphid_forecast_model.pkl"))
APHID_FORECAST_META_PATH = os.getenv("APHID_FORECAST_META_PATH", str(APP_DIR / "model" / "aphid_forecast_meta.json"))
DEFAULT_PRESSURE_HPA = float(os.getenv("DEFAULT_PRESSURE_HPA", "1013.25"))

BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_IMAGES = os.getenv("BLOB_CONTAINER_IMAGES", "aphid-images")
BLOB_CONTAINER_HISTORY = os.getenv("BLOB_CONTAINER_HISTORY", "aphid-history")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", BLOB_CONNECTION_STRING)
TELEMETRY_TABLE = os.getenv("TELEMETRY_TABLE", "iottelemetry")
APHID_COUNT_TABLE = os.getenv("APHID_COUNT_TABLE", "aphidcounts")
IOT_API_KEY = os.getenv("IOT_API_KEY", "")
TELEMETRY_DASHBOARD_PATH = os.getenv("TELEMETRY_DASHBOARD_PATH", str(APP_DIR / "telemetry_dashboard.html"))
PREDICT_DASHBOARD_PATH = os.getenv("PREDICT_DASHBOARD_PATH", str(APP_DIR / "local_web_client.html"))
HISTORY_DASHBOARD_PATH = os.getenv("HISTORY_DASHBOARD_PATH", str(APP_DIR / "history_records.html"))
DECISION_DASHBOARD_PATH = os.getenv("DECISION_DASHBOARD_PATH", str(APP_DIR / "decision_dashboard.html"))
FORECAST_DASHBOARD_PATH = os.getenv("FORECAST_DASHBOARD_PATH", str(APP_DIR / "forecast_dashboard.html"))
OPEN_METEO_FORECAST_URL = os.getenv("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
FORECAST_LOCATION_NAME = os.getenv("FORECAST_LOCATION_NAME", "London")
FORECAST_LATITUDE = float(os.getenv("FORECAST_LATITUDE", "51.5072"))
FORECAST_LONGITUDE = float(os.getenv("FORECAST_LONGITUDE", "-0.1276"))
FORECAST_TIMEZONE = os.getenv("FORECAST_TIMEZONE", "Europe/London")
WEATHER_REQUEST_TIMEOUT_SEC = int(os.getenv("WEATHER_REQUEST_TIMEOUT_SEC", "20"))

# Fail fast if the primary YOLO model is not available.
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

model = YOLO(MODEL_PATH)
app = FastAPI(title="Aphid YOLO26 Inference API", version="1.6.0")
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
aphid_count_table = None
aphid_count_table_error = ""
if AZURE_STORAGE_CONNECTION_STRING:
    try:
        table_service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    except Exception as exc:
        telemetry_init_error = str(exc)
        telemetry_table = None
        aphid_count_table = None
    else:
        try:
            table_service.create_table_if_not_exists(TELEMETRY_TABLE)
            telemetry_table = table_service.get_table_client(TELEMETRY_TABLE)
        except Exception as exc:
            telemetry_init_error = str(exc)
            telemetry_table = None

        try:
            table_service.create_table_if_not_exists(APHID_COUNT_TABLE)
            aphid_count_table = table_service.get_table_client(APHID_COUNT_TABLE)
        except Exception as exc:
            aphid_count_table_error = str(exc)
            aphid_count_table = None
else:
    telemetry_init_error = "AZURE_STORAGE_CONNECTION_STRING is empty."
    aphid_count_table_error = "AZURE_STORAGE_CONNECTION_STRING is empty."


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


class WeeklyAphidForecastIn(BaseModel):
    """Payload schema for weekly aphid trend forecasting."""

    aphid_count: int = Field(..., ge=0)
    exposure_days: int = Field(default=7, ge=1, le=14)
    week_start: date | None = None
    prev_catch_rate: float | None = Field(default=None, ge=0)
    t_mean: float = 15.0
    rh_mean: float = Field(default=70.0, ge=0, le=100)
    pressure_mean: float | None = Field(default=None, ge=850, le=1100)
    t_forecast: float = 15.0
    rh_forecast: float = Field(default=70.0, ge=0, le=100)
    pressure_forecast: float | None = Field(default=None, ge=850, le=1100)
    forecast_source: str | None = Field(default=None, min_length=1, max_length=128)
    forecast_generated_at: datetime | None = None


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
forecast_classifier = None
forecast_regressor = None
forecast_model_error = ""
forecast_meta: dict[str, Any] = {}
forecast_feature_cols: list[str] = [
    "log_catch",
    "catch_trend",
    "T_mean",
    "RH_mean",
    "pressure_mean",
    "VPD_mean",
    "T_forecast",
    "RH_forecast",
    "pressure_forecast",
    "VPD_forecast",
    "temp_delta",
    "rh_delta",
    "pressure_delta",
    "doy_sin",
    "doy_cos",
    "in_tepp_window",
]
forecast_stable_band = 0.3
forecast_data_source = "unknown"
forecast_real_rows_used = 0
forecast_synthetic_rows_used = 0


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


def _init_aphid_forecast_assets() -> None:
    """Load weekly aphid forecast model + meta from disk."""

    global forecast_classifier, forecast_regressor, forecast_model_error, forecast_meta
    global forecast_feature_cols, forecast_stable_band, forecast_data_source
    global forecast_real_rows_used, forecast_synthetic_rows_used

    forecast_classifier = None
    forecast_regressor = None
    forecast_model_error = ""
    forecast_meta = {}
    forecast_data_source = "unknown"
    forecast_real_rows_used = 0
    forecast_synthetic_rows_used = 0

    if os.path.exists(APHID_FORECAST_META_PATH):
        try:
            forecast_meta = _load_json_file(APHID_FORECAST_META_PATH)
            feature_cols = forecast_meta.get("feature_cols")
            if isinstance(feature_cols, list) and all(isinstance(c, str) for c in feature_cols):
                forecast_feature_cols = feature_cols
            forecast_stable_band = float(forecast_meta.get("stable_band", forecast_stable_band))
            data_summary = forecast_meta.get("data_summary", {})
            if isinstance(data_summary, dict):
                forecast_data_source = str(data_summary.get("source", forecast_data_source))
                forecast_real_rows_used = int(data_summary.get("rows_real", forecast_real_rows_used) or 0)
                forecast_synthetic_rows_used = int(data_summary.get("rows_synthetic", forecast_synthetic_rows_used) or 0)
        except Exception as exc:
            forecast_model_error = f"Forecast meta load failed: {exc}"

    if not os.path.exists(APHID_FORECAST_MODEL_PATH):
        if not forecast_model_error:
            forecast_model_error = f"Forecast model not found: {APHID_FORECAST_MODEL_PATH}"
        return

    try:
        with open(APHID_FORECAST_MODEL_PATH, "rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, dict):
            forecast_classifier = payload.get("classifier")
            forecast_regressor = payload.get("regressor")
            feature_cols = payload.get("feature_cols")
            if isinstance(feature_cols, list) and all(isinstance(c, str) for c in feature_cols):
                forecast_feature_cols = feature_cols
            forecast_stable_band = float(payload.get("stable_band", forecast_stable_band))
        else:
            forecast_classifier = payload
    except Exception as exc:
        forecast_classifier = None
        forecast_regressor = None
        if forecast_model_error:
            forecast_model_error = f"{forecast_model_error}; forecast model load failed: {exc}"
        else:
            forecast_model_error = f"Forecast model load failed: {exc}"


_init_aphid_forecast_assets()


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


def _resolve_week_start(week_start: date | None) -> date:
    """Resolve week_start or default to the current UTC week's Monday."""

    if week_start is not None:
        return week_start
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=today.weekday())


def _normalize_pressure_hpa(value: float | None) -> float:
    """Resolve nullable pressure input with a neutral default."""

    return float(DEFAULT_PRESSURE_HPA if value is None else value)


def _coerce_float(value: Any) -> float | None:
    """Convert a scalar into float when possible, otherwise return None."""

    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _mean_or_none(values: list[float]) -> float | None:
    """Return arithmetic mean for a non-empty float list."""

    if not values:
        return None
    return float(sum(values) / len(values))


def _parse_entity_ts(value: Any) -> datetime | None:
    """Parse telemetry/count timestamps into timezone-aware UTC datetimes."""

    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _query_recent_partition_entities(
    table_client: Any,
    partition_key: str,
    start_ts: datetime,
    *,
    max_rows: int = 5000,
) -> list[dict[str, Any]]:
    """Read recent rows for one partition until the iterator reaches data older than start_ts."""

    rows: list[dict[str, Any]] = []
    query_filter = "PartitionKey eq @partition_key"
    parameters = {"partition_key": partition_key}

    for entity in table_client.query_entities(query_filter=query_filter, parameters=parameters):
        parsed_ts = _parse_entity_ts(entity.get("ts"))
        if parsed_ts is None:
            continue
        if parsed_ts < start_ts:
            break
        row = dict(entity)
        row["_parsed_ts"] = parsed_ts
        rows.append(row)
        if len(rows) >= max_rows:
            break

    return rows


def _query_partition_window_entities(
    table_client: Any,
    partition_key: str,
    *,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Read rows for one partition and optionally filter them into a time window."""

    rows: list[dict[str, Any]] = []
    query_filter = "PartitionKey eq @partition_key"
    parameters = {"partition_key": partition_key}

    for entity in table_client.query_entities(query_filter=query_filter, parameters=parameters):
        parsed_ts = _parse_entity_ts(entity.get("ts"))
        if parsed_ts is None:
            continue
        if end_ts is not None and parsed_ts > end_ts:
            continue
        if start_ts is not None and parsed_ts < start_ts:
            break

        row = dict(entity)
        row["_parsed_ts"] = parsed_ts
        rows.append(row)
        if len(rows) >= limit:
            break

    return rows


def _split_rows_by_window(
    rows: list[dict[str, Any]],
    current_start: datetime,
    now_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into current window and immediately preceding comparison window."""

    previous_start = current_start - (now_utc - current_start)
    current_rows: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []

    for row in rows:
        parsed_ts = row.get("_parsed_ts")
        if not isinstance(parsed_ts, datetime):
            continue
        if current_start <= parsed_ts <= now_utc:
            current_rows.append(row)
        elif previous_start <= parsed_ts < current_start:
            previous_rows.append(row)

    return current_rows, previous_rows


def _summarize_recent_telemetry(device_id: str, days: int, now_utc: datetime) -> tuple[dict[str, Any], list[str]]:
    """Aggregate rolling telemetry means from Azure Table Storage."""

    warnings: list[str] = []
    current_start = now_utc - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    if telemetry_table is None:
        raise HTTPException(status_code=503, detail=f"Telemetry storage unavailable: {telemetry_init_error}")

    try:
        rows = _query_recent_partition_entities(telemetry_table, device_id, previous_start)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Telemetry query failed: {exc}") from exc

    current_rows, previous_rows = _split_rows_by_window(rows, current_start, now_utc)
    t_values = [v for v in (_coerce_float(r.get("temperature")) for r in current_rows) if v is not None]
    rh_values = [v for v in (_coerce_float(r.get("humidity")) for r in current_rows) if v is not None]
    pressure_values = [v for v in (_coerce_float(r.get("pressure_hpa")) for r in current_rows) if v is not None]
    current_days = sorted({r["_parsed_ts"].date().isoformat() for r in current_rows if isinstance(r.get("_parsed_ts"), datetime)})
    previous_days = sorted({r["_parsed_ts"].date().isoformat() for r in previous_rows if isinstance(r.get("_parsed_ts"), datetime)})

    if not current_rows:
        warnings.append(f"No telemetry rows were found for device '{device_id}' in the last {days} days.")
    elif len(current_days) < min(days, 3):
        warnings.append(f"Telemetry coverage is sparse for device '{device_id}' ({len(current_days)} day(s) over the last {days}).")

    return (
        {
            "device_id": device_id,
            "window_days": days,
            "current_start_utc": current_start.isoformat(),
            "current_end_utc": now_utc.isoformat(),
            "previous_start_utc": previous_start.isoformat(),
            "telemetry_rows_current": len(current_rows),
            "telemetry_rows_previous": len(previous_rows),
            "telemetry_days_current": current_days,
            "telemetry_days_previous": previous_days,
            "t_mean": _mean_or_none(t_values),
            "rh_mean": _mean_or_none(rh_values),
            "pressure_mean": _mean_or_none(pressure_values),
        },
        warnings,
    )


def _summarize_recent_aphid_counts(device_id: str, days: int, now_utc: datetime) -> tuple[dict[str, Any], list[str]]:
    """Aggregate rolling aphid count totals from Azure Table Storage."""

    warnings: list[str] = []
    current_start = now_utc - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    if aphid_count_table is None:
        raise HTTPException(status_code=503, detail=f"Aphid count storage unavailable: {aphid_count_table_error}")

    partitions_to_try = [device_id]
    if device_id != "default":
        partitions_to_try.append("default")

    selected_partition = device_id
    rows: list[dict[str, Any]] = []
    try:
        for partition_key in partitions_to_try:
            candidate_rows = _query_recent_partition_entities(aphid_count_table, partition_key, previous_start)
            if candidate_rows:
                rows = candidate_rows
                selected_partition = partition_key
                break
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Aphid count query failed: {exc}") from exc

    if rows and selected_partition != device_id:
        warnings.append(
            f"No aphid count rows were found under partition '{device_id}', so fallback partition '{selected_partition}' was used."
        )
    if not rows:
        warnings.append(f"No aphid count rows were found for '{device_id}' in the last {days * 2} days.")

    current_rows, previous_rows = _split_rows_by_window(rows, current_start, now_utc)
    current_counts = [v for v in (_coerce_float(r.get("count")) for r in current_rows) if v is not None]
    previous_counts = [v for v in (_coerce_float(r.get("count")) for r in previous_rows) if v is not None]
    current_days = sorted({r["_parsed_ts"].date().isoformat() for r in current_rows if isinstance(r.get("_parsed_ts"), datetime)})
    previous_days = sorted({r["_parsed_ts"].date().isoformat() for r in previous_rows if isinstance(r.get("_parsed_ts"), datetime)})

    if not current_rows:
        warnings.append(f"No aphid detection rows were found in the current {days}-day window for '{selected_partition}'.")
    if not previous_rows:
        warnings.append("No aphid detection rows were found in the previous comparison window; catch trend will fall back to 0.0.")

    aphid_count = int(round(sum(current_counts))) if current_counts else 0
    exposure_days = len(current_days) if current_days else min(days, 7)
    previous_exposure_days = len(previous_days)
    prev_catch_rate = None
    if previous_exposure_days > 0:
        prev_catch_rate = float(sum(previous_counts) / previous_exposure_days)

    return (
        {
            "device_id": device_id,
            "partition_used": selected_partition,
            "window_days": days,
            "current_start_utc": current_start.isoformat(),
            "current_end_utc": now_utc.isoformat(),
            "previous_start_utc": previous_start.isoformat(),
            "aphid_rows_current": len(current_rows),
            "aphid_rows_previous": len(previous_rows),
            "aphid_days_current": current_days,
            "aphid_days_previous": previous_days,
            "aphid_count": aphid_count,
            "exposure_days": exposure_days,
            "prev_catch_rate": prev_catch_rate,
            "previous_count_total": round(float(sum(previous_counts)), 4),
        },
        warnings,
    )


def _fetch_london_weather_forecast(days: int, observed_weather: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fetch mean forecast weather for London and fall back to recent observed weather when needed."""

    warnings: list[str] = []
    fetched_at = datetime.now(timezone.utc)
    observed_t_mean = _coerce_float(observed_weather.get("t_mean"))
    observed_rh_mean = _coerce_float(observed_weather.get("rh_mean"))
    observed_pressure_mean = _coerce_float(observed_weather.get("pressure_mean"))
    fallback = {
        "t_forecast": float(15.0 if observed_t_mean is None else observed_t_mean),
        "rh_forecast": float(70.0 if observed_rh_mean is None else observed_rh_mean),
        "pressure_forecast": float(DEFAULT_PRESSURE_HPA if observed_pressure_mean is None else observed_pressure_mean),
        "forecast_source": "observed_weather_fallback",
        "forecast_generated_at": fetched_at,
        "location_name": FORECAST_LOCATION_NAME,
        "location": {
            "latitude": FORECAST_LATITUDE,
            "longitude": FORECAST_LONGITUDE,
            "timezone": FORECAST_TIMEZONE,
        },
        "fallback_used": True,
    }

    params = {
        "latitude": FORECAST_LATITUDE,
        "longitude": FORECAST_LONGITUDE,
        "timezone": FORECAST_TIMEZONE,
        "forecast_days": days,
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,pressure_msl_mean",
    }

    try:
        response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=WEATHER_REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        payload = response.json()
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise ValueError("Weather response did not include a daily forecast block.")

        t_values_raw = daily.get("temperature_2m_mean") or []
        rh_values_raw = daily.get("relative_humidity_2m_mean") or []
        pressure_values_raw = daily.get("pressure_msl_mean") or []
        t_values = [v for v in (_coerce_float(v) for v in t_values_raw) if v is not None]
        rh_values = [v for v in (_coerce_float(v) for v in rh_values_raw) if v is not None]
        pressure_values = [v for v in (_coerce_float(v) for v in pressure_values_raw) if v is not None]

        horizon = min(days, len(t_values), len(rh_values), len(pressure_values))
        if horizon <= 0:
            raise ValueError("Weather response did not include enough forecast values.")

        return (
            {
                "t_forecast": float(sum(t_values[:horizon]) / horizon),
                "rh_forecast": float(sum(rh_values[:horizon]) / horizon),
                "pressure_forecast": float(sum(pressure_values[:horizon]) / horizon),
                "forecast_source": "open-meteo",
                "forecast_generated_at": fetched_at,
                "location_name": FORECAST_LOCATION_NAME,
                "location": {
                    "latitude": payload.get("latitude", FORECAST_LATITUDE),
                    "longitude": payload.get("longitude", FORECAST_LONGITUDE),
                    "timezone": payload.get("timezone", FORECAST_TIMEZONE),
                },
                "fallback_used": False,
            },
            warnings,
        )
    except Exception as exc:
        warnings.append(f"London forecast fetch failed; falling back to recent observed weather. reason={exc}")
        return fallback, warnings


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    """Merge multiple string lists while preserving first-seen order."""

    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if not item or item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


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


def _build_forecast_feature_map(payload: WeeklyAphidForecastIn) -> dict[str, float | str]:
    """Transform forecast payload into model-ready weekly features."""

    current_week_start = _resolve_week_start(payload.week_start)
    prediction_week_start = current_week_start + timedelta(days=7)
    prediction_doy = prediction_week_start.timetuple().tm_yday
    pressure_mean = _normalize_pressure_hpa(payload.pressure_mean)
    pressure_forecast = _normalize_pressure_hpa(payload.pressure_forecast)

    catch_rate = float(payload.aphid_count) / float(payload.exposure_days)
    catch_trend = (
        catch_rate - float(payload.prev_catch_rate)
        if payload.prev_catch_rate is not None
        else 0.0
    )
    vpd_mean = _vpd_kpa(float(payload.t_mean), float(payload.rh_mean))
    vpd_forecast = _vpd_kpa(float(payload.t_forecast), float(payload.rh_forecast))

    return {
        "catch_rate": catch_rate,
        "log_catch": math.log1p(catch_rate),
        "catch_trend": catch_trend,
        "T_mean": float(payload.t_mean),
        "RH_mean": float(payload.rh_mean),
        "pressure_mean": pressure_mean,
        "VPD_mean": float(vpd_mean),
        "T_forecast": float(payload.t_forecast),
        "RH_forecast": float(payload.rh_forecast),
        "pressure_forecast": pressure_forecast,
        "VPD_forecast": float(vpd_forecast),
        "temp_delta": float(payload.t_forecast) - float(payload.t_mean),
        "rh_delta": float(payload.rh_forecast) - float(payload.rh_mean),
        "pressure_delta": pressure_forecast - pressure_mean,
        "doy_sin": math.sin(2.0 * math.pi * prediction_doy / 365.25),
        "doy_cos": math.cos(2.0 * math.pi * prediction_doy / 365.25),
        "in_tepp_window": float(_resolve_tepp_window(prediction_doy, None)),
        "doy": float(prediction_doy),
        "prediction_week_start": prediction_week_start.isoformat(),
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


def _forecast_trend_label(trend_class: int) -> str:
    """Map forecast class into API-facing semantic label."""

    return {1: "up", 0: "stable", -1: "down"}.get(int(trend_class), "stable")


def _forecast_class_probabilities(features: list[float]) -> dict[str, float] | None:
    """Return forecast trend class probabilities when the model supports predict_proba."""

    if forecast_classifier is None or not hasattr(forecast_classifier, "predict_proba"):
        return None
    try:
        proba = forecast_classifier.predict_proba([features])[0]
    except Exception:
        return None

    classes_raw = getattr(forecast_classifier, "classes_", None)
    if classes_raw is None and hasattr(forecast_classifier, "named_steps"):
        clf = forecast_classifier.named_steps.get("clf")
        if clf is not None:
            classes_raw = getattr(clf, "classes_", None)
    if classes_raw is None:
        return None

    out: dict[str, float] = {}
    for idx, cls_id in enumerate(classes_raw):
        if idx >= len(proba):
            continue
        out[str(int(cls_id))] = float(proba[idx])
    return out


def _predict_forecast_with_model(features: list[float]) -> tuple[int | None, float | None]:
    """Infer forecast trend class and next catch-rate estimate from loaded assets."""

    if forecast_classifier is None or forecast_regressor is None:
        return None, None
    try:
        trend_class = int(forecast_classifier.predict([features])[0])
        next_log_catch = float(forecast_regressor.predict([features])[0])
        next_catch_rate = max(math.exp(next_log_catch) - 1.0, 0.0)
        return trend_class, next_catch_rate
    except Exception:
        return None, None


def _heuristic_forecast(feature_map: dict[str, float | str]) -> tuple[int, float, float]:
    """Fallback forecast heuristic used when the trained model is unavailable."""

    catch_rate = float(feature_map["catch_rate"])
    score = (
        0.65 * float(feature_map["catch_trend"])
        + 0.05 * float(feature_map["temp_delta"])
        + 0.012 * float(feature_map["rh_delta"])
        + 0.02 * (float(feature_map["pressure_mean"]) - float(feature_map["pressure_forecast"]))
        + 0.22 * float(feature_map["log_catch"])
        + 0.18 * float(feature_map["in_tepp_window"])
    )
    next_catch_rate = max(catch_rate + 0.35 * score, 0.0)
    delta = next_catch_rate - catch_rate
    if delta > forecast_stable_band:
        trend_class = 1
    elif delta < -forecast_stable_band:
        trend_class = -1
    else:
        trend_class = 0
    confidence = min(0.95, 0.5 + abs(delta) / max(forecast_stable_band * 3.0, 0.3))
    return trend_class, next_catch_rate, float(confidence)


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
        "telemetry_table": TELEMETRY_TABLE,
        "telemetry_init_error": telemetry_init_error or None,
        "aphid_count_enabled": aphid_count_table is not None,
        "aphid_count_table": APHID_COUNT_TABLE,
        "aphid_count_error": aphid_count_table_error or None,
        "tepp_demo_model_enabled": tepp_model is not None,
        "tepp_demo_model_path": TEPP_DEMO_MODEL_PATH,
        "tepp_demo_meta_path": TEPP_DEMO_META_PATH,
        "tepp_demo_model_error": tepp_model_error or None,
        "forecast_model_enabled": forecast_classifier is not None and forecast_regressor is not None,
        "forecast_model_path": APHID_FORECAST_MODEL_PATH,
        "forecast_meta_path": APHID_FORECAST_META_PATH,
        "forecast_model_error": forecast_model_error or None,
        "forecast_weather_source": OPEN_METEO_FORECAST_URL,
        "forecast_weather_location": FORECAST_LOCATION_NAME,
    }


@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    conf: float = DEFAULT_CONF,
    iou: float = DEFAULT_IOU,
    imgsz: int = DEFAULT_IMGSZ,
    max_det: int = DEFAULT_MAX_DET,
    device_id: str | None = Query(default=None, min_length=1, max_length=64),
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
    ts_now = datetime.now(timezone.utc)
    aphid_partition = device_id.strip() if isinstance(device_id, str) and device_id.strip() else "default"
    history_payload: dict[str, Any] = {
        "request_id": request_id,
        "timestamp_utc": ts_now.isoformat(),
        "filename": image.filename,
        "device_id": device_id,
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

    aphid_count_saved = False
    aphid_count_error = None
    if aphid_count_table is not None:
        count_entity = {
            "PartitionKey": aphid_partition,
            "RowKey": _desc_row_key(ts_now),
            "device_id": aphid_partition,
            "source_device_id": device_id,
            "request_id": request_id,
            "ts": ts_now.isoformat(),
            "filename": image.filename,
            "count": len(detections),
            "image_blob_name": image_blob_name if image_url else None,
            "history_blob_name": history_blob_name if history_url else None,
            "created_at": ts_now.isoformat(),
        }
        try:
            aphid_count_table.upsert_entity(entity=count_entity)
            aphid_count_saved = True
        except Exception as exc:
            aphid_count_error = str(exc)
    else:
        aphid_count_error = aphid_count_table_error or "Aphid count table is not configured."

    response = {
        "request_id": request_id,
        "filename": image.filename,
        "device_id": device_id,
        "count": len(detections),
        "detections": detections,
        "blob_saved": storage_error is None,
        "history_saved": history_error is None,
        "aphid_count_table_saved": aphid_count_saved,
        "aphid_count_partition": aphid_partition,
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
    if aphid_count_error:
        response["aphid_count_table_error"] = aphid_count_error
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


@app.get("/grafana/telemetry")
def grafana_telemetry(
    device_id: str = Query(..., min_length=1),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Return raw telemetry rows for Grafana or other HTTP/JSON consumers."""

    _check_iot_api_key(x_api_key)

    if telemetry_table is None:
        raise HTTPException(status_code=503, detail=f"Telemetry storage unavailable: {telemetry_init_error}")

    start_utc = from_ts.astimezone(timezone.utc) if from_ts is not None else None
    end_utc = to_ts.astimezone(timezone.utc) if to_ts is not None else None
    rows = _query_partition_window_entities(
        telemetry_table,
        device_id,
        start_ts=start_utc,
        end_ts=end_utc,
        limit=limit,
    )

    items = [
        {
            "device_id": row.get("device_id"),
            "ts": row.get("ts"),
            "temperature": row.get("temperature"),
            "humidity": row.get("humidity"),
            "pressure_hpa": row.get("pressure_hpa"),
            "light": row.get("light"),
        }
        for row in rows
    ]

    return {
        "device_id": device_id,
        "from": start_utc.isoformat() if start_utc is not None else None,
        "to": end_utc.isoformat() if end_utc is not None else None,
        "count": len(items),
        "items": items,
    }


@app.get("/grafana/aphidcounts")
def grafana_aphidcounts(
    device_id: str = Query(..., min_length=1),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    """Return raw aphid count rows for Grafana or other HTTP/JSON consumers."""

    if aphid_count_table is None:
        raise HTTPException(status_code=503, detail=f"Aphid count storage unavailable: {aphid_count_table_error}")

    start_utc = from_ts.astimezone(timezone.utc) if from_ts is not None else None
    end_utc = to_ts.astimezone(timezone.utc) if to_ts is not None else None
    rows = _query_partition_window_entities(
        aphid_count_table,
        device_id,
        start_ts=start_utc,
        end_ts=end_utc,
        limit=limit,
    )

    items = [
        {
            "device_id": row.get("device_id"),
            "source_device_id": row.get("source_device_id"),
            "request_id": row.get("request_id"),
            "ts": row.get("ts"),
            "filename": row.get("filename"),
            "count": row.get("count"),
            "image_blob_name": row.get("image_blob_name"),
            "history_blob_name": row.get("history_blob_name"),
        }
        for row in rows
    ]

    return {
        "device_id": device_id,
        "from": start_utc.isoformat() if start_utc is not None else None,
        "to": end_utc.isoformat() if end_utc is not None else None,
        "count": len(items),
        "items": items,
    }


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


@app.post("/forecast/weekly")
def weekly_aphid_forecast(payload: WeeklyAphidForecastIn) -> dict[str, Any]:
    """Predict next week's aphid trend and next-count estimate from observed + forecast weather."""

    feature_map = _build_forecast_feature_map(payload)
    feature_values = [float(feature_map.get(c, 0.0)) for c in forecast_feature_cols]

    trend_class, next_catch_rate_est = _predict_forecast_with_model(feature_values)
    class_probabilities = _forecast_class_probabilities(feature_values)
    model_source = "aphid_forecast_model"
    trend_confidence: float | None = None

    if class_probabilities:
        trend_confidence = max(float(v) for v in class_probabilities.values())

    if trend_class is None or next_catch_rate_est is None:
        trend_class, next_catch_rate_est, heuristic_conf = _heuristic_forecast(feature_map)
        class_probabilities = None
        trend_confidence = heuristic_conf
        model_source = "teacher_rule_fallback"

    next_count_estimate = int(max(0, round(float(next_catch_rate_est) * float(payload.exposure_days))))
    delta_catch_rate = float(next_catch_rate_est) - float(feature_map["catch_rate"])
    warnings: list[str] = []
    if payload.prev_catch_rate is None:
        warnings.append("prev_catch_rate was omitted; catch_trend defaulted to 0.0.")
    if payload.pressure_mean is None or payload.pressure_forecast is None:
        warnings.append("pressure_mean and/or pressure_forecast were missing; defaults of 1013.25 hPa were applied.")
    if forecast_data_source != "real_only" or forecast_real_rows_used < 8:
        warnings.append("Forecast reliability is limited because the model still depends heavily on synthetic training rows.")
    if payload.forecast_source is None:
        warnings.append("forecast_source was not provided, so forecast provenance is not recorded.")
    if trend_confidence is not None and float(trend_confidence) < 0.6:
        warnings.append("Trend confidence is low; treat this as an early warning rather than a hard decision signal.")

    response: dict[str, Any] = {
        "trend_class": int(trend_class),
        "trend_label": _forecast_trend_label(int(trend_class)),
        "trend_confidence": None if trend_confidence is None else round(float(trend_confidence), 4),
        "next_count_estimate": next_count_estimate,
        "next_catch_rate_estimate": round(float(next_catch_rate_est), 4),
        "delta_catch_rate_estimate": round(delta_catch_rate, 4),
        "warnings": warnings,
        "inputs": {
            "aphid_count": payload.aphid_count,
            "exposure_days": payload.exposure_days,
            "catch_rate": round(float(feature_map["catch_rate"]), 4),
            "catch_trend": round(float(feature_map["catch_trend"]), 4),
            "t_mean": round(float(feature_map["T_mean"]), 3),
            "rh_mean": round(float(feature_map["RH_mean"]), 3),
            "pressure_mean": round(float(feature_map["pressure_mean"]), 3),
            "vpd_mean": round(float(feature_map["VPD_mean"]), 4),
            "t_forecast": round(float(feature_map["T_forecast"]), 3),
            "rh_forecast": round(float(feature_map["RH_forecast"]), 3),
            "pressure_forecast": round(float(feature_map["pressure_forecast"]), 3),
            "vpd_forecast": round(float(feature_map["VPD_forecast"]), 4),
            "temp_delta": round(float(feature_map["temp_delta"]), 4),
            "rh_delta": round(float(feature_map["rh_delta"]), 4),
            "pressure_delta": round(float(feature_map["pressure_delta"]), 4),
            "forecast_source": payload.forecast_source,
            "forecast_generated_at": None if payload.forecast_generated_at is None else payload.forecast_generated_at.isoformat(),
            "prediction_week_start": str(feature_map["prediction_week_start"]),
            "week_start_doy": int(feature_map["doy"]),
            "in_tepp_window": int(float(feature_map["in_tepp_window"])),
        },
        "model": {
            "source": model_source,
            "loaded": forecast_classifier is not None and forecast_regressor is not None,
            "feature_cols": forecast_feature_cols,
            "stable_band": forecast_stable_band,
            "data_source": forecast_data_source,
            "real_rows_used": forecast_real_rows_used,
            "synthetic_rows_used": forecast_synthetic_rows_used,
            "class_probabilities": class_probabilities,
            "error": forecast_model_error or None,
        },
    }
    return response


@app.get("/forecast/auto")
def auto_weekly_aphid_forecast(
    device_id: str = Query(..., min_length=1, max_length=64),
    days: int = Query(7, ge=3, le=14),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Build forecast inputs from Azure tables + London weather and reuse the weekly forecast model."""

    _check_iot_api_key(x_api_key)

    now_utc = datetime.now(timezone.utc)
    telemetry_summary, telemetry_warnings = _summarize_recent_telemetry(device_id, days, now_utc)
    aphid_summary, aphid_warnings = _summarize_recent_aphid_counts(device_id, days, now_utc)
    weather_summary, weather_warnings = _fetch_london_weather_forecast(days, telemetry_summary)

    auto_warnings = _merge_unique_strings(telemetry_warnings, aphid_warnings, weather_warnings)
    t_mean = telemetry_summary.get("t_mean")
    rh_mean = telemetry_summary.get("rh_mean")
    pressure_mean = telemetry_summary.get("pressure_mean")

    if t_mean is None:
        auto_warnings.append("t_mean could not be derived from telemetry; a neutral default of 15.0C was applied.")
        t_mean = 15.0
    if rh_mean is None:
        auto_warnings.append("rh_mean could not be derived from telemetry; a neutral default of 70.0% was applied.")
        rh_mean = 70.0
    if pressure_mean is None:
        auto_warnings.append(f"pressure_mean could not be derived from telemetry; a neutral default of {DEFAULT_PRESSURE_HPA} hPa was applied.")
        pressure_mean = DEFAULT_PRESSURE_HPA

    payload = WeeklyAphidForecastIn(
        aphid_count=int(aphid_summary.get("aphid_count") or 0),
        exposure_days=int(aphid_summary.get("exposure_days") or min(days, 7)),
        week_start=(now_utc - timedelta(days=days)).date(),
        prev_catch_rate=aphid_summary.get("prev_catch_rate"),
        t_mean=float(t_mean),
        rh_mean=float(rh_mean),
        pressure_mean=float(pressure_mean),
        t_forecast=float(weather_summary["t_forecast"]),
        rh_forecast=float(weather_summary["rh_forecast"]),
        pressure_forecast=float(weather_summary["pressure_forecast"]),
        forecast_source=str(weather_summary["forecast_source"]),
        forecast_generated_at=weather_summary["forecast_generated_at"],
    )

    result = weekly_aphid_forecast(payload)
    result["warnings"] = _merge_unique_strings(auto_warnings, list(result.get("warnings") or []))
    result["data_quality"] = (
        "ok"
        if (
            int(telemetry_summary.get("telemetry_rows_current") or 0) > 0
            and int(aphid_summary.get("aphid_rows_current") or 0) > 0
            and int(aphid_summary.get("aphid_rows_previous") or 0) > 0
            and not bool(weather_summary.get("fallback_used"))
        )
        else "sparse"
    )
    result["auto_context"] = {
        "device_id": device_id,
        "window_days": days,
        "telemetry": telemetry_summary,
        "aphid_counts": aphid_summary,
        "weather_forecast": {
            "location_name": weather_summary.get("location_name"),
            "location": weather_summary.get("location"),
            "forecast_source": weather_summary.get("forecast_source"),
            "forecast_generated_at": weather_summary["forecast_generated_at"].isoformat(),
            "fallback_used": bool(weather_summary.get("fallback_used")),
        },
    }
    return result


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


@app.get("/forecast/dashboard")
def forecast_dashboard() -> FileResponse:
    """Serve weekly forecast dashboard HTML bundled in container image."""

    if not os.path.exists(FORECAST_DASHBOARD_PATH):
        raise HTTPException(status_code=404, detail="Dashboard not found in container image.")
    return FileResponse(FORECAST_DASHBOARD_PATH)
