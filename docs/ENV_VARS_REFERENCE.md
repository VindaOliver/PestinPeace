# Environment Variables Reference

This is the central list of server environment variables used by `apps/api/container/server.py`.

## Model And Inference

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_PATH` | `/app/model/best.pt` in Docker | YOLO aphid/slug detector path |
| `DEFAULT_CONF` | `0.25` | Default YOLO confidence threshold |
| `DEFAULT_IOU` | `0.45` | Default YOLO IoU threshold |
| `DEFAULT_IMGSZ` | `640` | Default inference image size |
| `DEFAULT_MAX_DET` | `1000` | Default max detections |
| `MAX_UPLOAD_BYTES` | `50000000` | Max uploaded image size before returning 413 |

## Decision And Forecast Models

| Variable | Default | Purpose |
|---|---|---|
| `TEPP_DEMO_MODEL_PATH` | `model/tepp_demo_scope_model.pkl` | Spray decision model |
| `TEPP_DEMO_META_PATH` | `model/tepp_demo_meta.json` | Spray decision metadata |
| `TEPP_DEFAULT_RATE_KG_HA` | `0.14` | Default product rate |
| `SPRAY_NOZZLE_MODEL` | `Hunter MP1000 Rotator Nozzle` | Display name for nozzle conversion |
| `SPRAY_NOZZLE_ARC_DEG` | `90` | Demo nozzle arc used for runtime conversion |
| `SPRAY_NOZZLE_PRESSURE_PSI` | `40` | Demo nozzle operating pressure |
| `SPRAY_NOZZLE_FLOW_GPM` | `0.21` | Demo nozzle flow rate; MP1000 90 degree arc at 40 PSI |
| `APHID_FORECAST_MODEL_PATH` | `model/aphid_forecast_model.pkl` | Forecast model |
| `APHID_FORECAST_META_PATH` | `model/aphid_forecast_meta.json` | Forecast model metadata |
| `DEFAULT_PRESSURE_HPA` | `1013.25` | Fallback pressure value |

If the nozzle arc or pressure is changed on real hardware, update `SPRAY_NOZZLE_FLOW_GPM` from a cup test or the nozzle data sheet. The API uses the flow value directly for `nozzle.runtime_sec`.

## Azure Storage

| Variable | Default | Purpose |
|---|---|---|
| `BLOB_CONNECTION_STRING` | empty | Blob storage connection string for images/history |
| `BLOB_CONTAINER_IMAGES` | `aphid-images` | Container for uploaded/annotated images |
| `BLOB_CONTAINER_HISTORY` | `aphid-history` | Container for prediction history JSON |
| `AZURE_STORAGE_CONNECTION_STRING` | `BLOB_CONNECTION_STRING` | Table storage connection string |
| `TELEMETRY_TABLE` | `iottelemetry` | Table for sensor data |
| `APHID_COUNT_TABLE` | `aphidcounts` | Table for aphid/slug detection counts |
| `DECISION_HISTORY_TABLE` | `decisionhistory` | Table for spray decision history |

## API Protection And Dashboards

| Variable | Default | Purpose |
|---|---|---|
| `IOT_API_KEY` | empty | Optional API key for protected write/read endpoints. When empty, demo endpoints are easier to call. |
| `TELEMETRY_DASHBOARD_PATH` | container HTML path | Telemetry dashboard file |
| `PREDICT_DASHBOARD_PATH` | container HTML path | Predict dashboard file |
| `HISTORY_DASHBOARD_PATH` | container HTML path | History dashboard file |
| `DECISION_DASHBOARD_PATH` | container HTML path | Decision dashboard file |
| `FORECAST_DASHBOARD_PATH` | container HTML path | Forecast dashboard file |

## Weather And Retry

| Variable | Default | Purpose |
|---|---|---|
| `OPEN_METEO_FORECAST_URL` | `https://api.open-meteo.com/v1/forecast` | Weather forecast source |
| `FORECAST_LOCATION_NAME` | `London` | Display name for forecast location |
| `FORECAST_LATITUDE` | `51.5072` | Forecast latitude |
| `FORECAST_LONGITUDE` | `-0.1276` | Forecast longitude |
| `FORECAST_TIMEZONE` | `Europe/London` | Forecast timezone |
| `WEATHER_REQUEST_TIMEOUT_SEC` | `20` | Weather request timeout |
| `REQUEST_RETRY_ATTEMPTS` | `3` | General retry attempts |
| `REQUEST_RETRY_BACKOFF_SEC` | `0.75` | General retry backoff |
| `AZURE_RETRY_ATTEMPTS` | `3` | Azure operation retry attempts |
| `AZURE_RETRY_BACKOFF_SEC` | `0.4` | Azure retry backoff |
| `LOG_LEVEL` | `INFO` | Server logging level |

## Current PAYG Table Names

The current deployed PAYG environment uses:

- `iottelemetry`
- `aphidcounts`
- `decisionhistory`

Business data should be read through the API layer, especially from the `/grafana/*` endpoints, rather than by giving teammates raw storage keys.
