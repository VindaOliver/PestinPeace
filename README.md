# PestinPeace (Azure YOLO + IoT)

This project provides:

1. YOLO image inference API for aphid detection (`/predict`)
2. IoT telemetry ingest/query APIs (`/telemetry`, `/telemetry/latest`)
3. Prediction history storage in Blob (`aphid-history`) with query API (`/history`)
4. Web pages for Predict / Monitor / History / Decision / Forecast
5. Weekly forecast and decision APIs (`/forecast/weekly`, `/decision/weekly`)
6. Grafana-facing API endpoints for business data (`/grafana/telemetry`, `/grafana/aphidcounts`, `/grafana/decisionhistory`)

Start here if you are onboarding or preparing a demo:

- Docs index: `docs/README.md`
- Current status and testing summary: `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
- Defense assets: `defense_assets/README_CN.md`

## 1. Live Service

Base URL:

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 2. API Endpoints

### 2.1 Health

- `GET /health`
- `GET /ready`

Example:

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/health"
```

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/ready"
```

### 2.2 Predict (YOLO Inference)

- `POST /predict`
- Content type: `multipart/form-data`
- Required field: `image`
- Required query param:
  - `device_id`
- Optional query params:
  - `conf` (default `0.25`)
  - `iou` (default `0.45`)
  - `imgsz` (default `640`)
  - `max_det` (default `1000`)
- Current validation bounds:
  - `conf`: `0.0` to `1.0`
  - `iou`: `0.0` to `1.0`
  - `imgsz`: `32` to `1280`
  - `max_det`: `1` to `5000`

Example:

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict?device_id=demo-trap-001&conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

Important response fields now include:

- `count`
- `detections`
- `count_mean`
- `images_in_round`
- `aggregation_mode`

### 2.3 IoT Telemetry Upload

- `POST /telemetry`
- Content type: `application/json`
- Body fields:
  - `device_id` (required)
  - `temperature` (optional)
  - `humidity` (optional)
  - `light` (optional)
  - `ts` (optional ISO datetime)
- Optional header:
  - `X-API-Key` (required only if `IOT_API_KEY` is set)

Example:

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d "{\"device_id\":\"pi-001\",\"temperature\":24.6,\"humidity\":58.2,\"light\":301}"
```

### 2.4 IoT Telemetry Query

- `GET /telemetry/latest?device_id=<id>&limit=<n>`
- `limit` default `100`, max `500`
- Optional header: `X-API-Key`

Example:

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/telemetry/latest?device_id=pi-001&limit=10"
```

### 2.5 Grafana API Query Endpoints

These endpoints are intended for Grafana or other HTTP/JSON consumers that need direct access to Azure Table data through the API layer.

- `GET /grafana/telemetry?device_id=<id>&from=<iso>&to=<iso>&limit=<n>`
- `GET /grafana/aphidcounts?device_id=<id>&from=<iso>&to=<iso>&limit=<n>`
- `GET /grafana/decisionhistory?device_id=<id>&from=<iso>&to=<iso>&limit=<n>`

Examples:

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/grafana/telemetry?device_id=pi-001&limit=50"
```

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/grafana/aphidcounts?device_id=pi-001&limit=50"
```

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/grafana/decisionhistory?device_id=pi-001&limit=20"
```

### 2.6 Decision History and Trend

- `GET /decision/history?device_id=<id>&limit=<n>`
- `GET /predict/trend?device_id=<id>&days=<n>`
- `GET /decision/history` returns decision records and summary flags such as:
  - `last_uploaded_record_is_spray`
  - `last_uploaded_record_should_spray`
- `GET /predict/trend` returns daily pest-count trend data for plotting or quick interpretation

Examples:

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/decision/history?device_id=demo-trap-001&limit=10"
```

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict/trend?device_id=demo-trap-001&days=31"
```

### 2.7 Prediction History Query

- `GET /history?limit=<n>`
- Reads history JSON blobs from `aphid-history`
- `limit` default `50`, max `500`

Example:

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/history?limit=50"
```

### 2.8 Built-in Dashboards (Container App routes)

- Predict dashboard: `GET /predict/dashboard`
- Telemetry dashboard: `GET /telemetry/dashboard`
- History dashboard: `GET /history/dashboard`
- Decision dashboard: `GET /decision/dashboard`
- Forecast dashboard: `GET /forecast/dashboard`

### 2.9 Weekly Decision (Demo Scope Model)

- `POST /decision/weekly`
- Content type: `application/json`
- Required fields:
  - `aphid_count`
  - `field_area_ha`
- Optional fields:
  - `exposure_days` (default `7`)
  - `week_start` (YYYY-MM-DD; used for season encoding/window inference)
  - `prev_catch_rate` or `catch_trend`
  - `t_mean`, `rh_mean`, `vpd_mean`
  - `in_tepp_window` (`0/1`; if omitted, inferred by day-of-year)
  - `apps_so_far` (default `0`)
  - `respect_compliance_gate` (default `true`)

Response includes:

- `scope_class` (`0=no_spray`, `1=boundary_band`, `2=full_field`)
- `treated_fraction` and `water_l_ha`
- `product_kg = 0.14 * area_ha * treated_fraction`
- `spray_l = water_l_ha * area_ha * treated_fraction`
- compliance gate result and model source (`tepp_demo_scope_model` or fallback rule)

Example:

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/decision/weekly" \
  -H "Content-Type: application/json" \
  -d "{\"aphid_count\":18,\"field_area_ha\":2.0,\"exposure_days\":7,\"t_mean\":16.4,\"rh_mean\":72,\"apps_so_far\":0}"
```

## 3. Local Web Pages

Web pages are under:

- `apps/web/web_pages/local_web_client.html` (Predict)
- `apps/web/web_pages/telemetry_dashboard.html` (Monitor)
- `apps/web/web_pages/history_records.html` (History)

Run local static server from repo root:

```bash
python -m http.server 18090
```

Open:

- `http://127.0.0.1:18090/apps/web/web_pages/local_web_client.html`
- `http://127.0.0.1:18090/apps/web/web_pages/telemetry_dashboard.html`
- `http://127.0.0.1:18090/apps/web/web_pages/history_records.html`

Top navigation is linked across all three pages.

## 3.1 Project Layout (Industry-style)

- `apps/api/container/`: FastAPI service, Dockerfile, runtime model artifacts
- `apps/web/web_pages/`: static dashboards for predict/telemetry/history
- `ml/yolo/`: YOLO training scripts/config/base checkpoint
- `ml/tepp/`: synthetic weekly decision model training script
- `scripts/deploy/`: deployment and packaging scripts
- `clients/raspberry_pi/`: Python client utilities for device-side integration
- `docs/`: operational and workflow documentation
- `third_party/`: vendor/external code (kept separate)

Detailed structure note: `docs/PROJECT_STRUCTURE.md`.
Documentation index: `docs/README.md`.
Current system summary: `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`.

## 4. Azure Resources (Current)

Resource group: `rg-aphid-yolo-payg`  
Region: `swedencentral`

Main resources:

- Container App: `aca-aphid-yolo`
- Container Apps Environment: `aca-env-aphid-yolo`
- Container Registry (ACR): `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Log Analytics Workspace: `workspace-rgaphidyolopaygK1ST`

Note:

- Azure still uses Log Analytics for platform logs.
- Grafana business-data queries now go through the API, not Log Analytics custom tables.

## 5. Storage Behavior

- `/predict` uploads source image to Blob container `aphid-images`.
- `/predict` also writes one JSON history record to Blob container `aphid-history`.
- `/telemetry` writes sensor records into Azure Table `iottelemetry`.
- Current deployment uses one storage account connection for both image/history blobs and telemetry table.

## 6. CI/CD (GitHub Actions + ACR + Container App)

Workflow:

- `.github/workflows/deploy_containerapp.yml`

Trigger:

- push to `main`
- manual `workflow_dispatch`

Pipeline:

1. Checkout
2. Sync `apps/web/web_pages/*.html` into `apps/api/container/`
3. Build Docker image
4. Push image to ACR
5. Update Container App image
6. Health check

## 7. Update Model

1. Replace model:
   - `apps/api/container/model/best.pt`
2. Optional demo decision artifacts (for `/decision/weekly` model mode):
   - `apps/api/container/model/tepp_demo_scope_model.pkl`
   - `apps/api/container/model/tepp_demo_meta.json`
3. Commit and push:
   - `git add .`
   - `git commit -m "Update model"`
   - `git push origin main`
4. Wait for workflow success.
5. Verify `/health`, `/predict`, and `/decision/weekly`.

## 8. Key Files

- `apps/api/container/server.py`
- `apps/api/container/Dockerfile`
- `apps/api/container/requirements.txt`
- `apps/api/container/model/best.pt`
- `apps/api/container/model/tepp_demo_scope_model.pkl` (optional)
- `apps/api/container/model/tepp_demo_meta.json` (optional)
- `apps/web/web_pages/local_web_client.html`
- `apps/web/web_pages/telemetry_dashboard.html`
- `apps/web/web_pages/history_records.html`
- `scripts/deploy/package_yolo26_container.py`
- `scripts/deploy/deploy_to_azure.ps1`
- `.github/workflows/deploy_containerapp.yml`

## 9. Troubleshooting

1. `/predict` fails
   - Check Container App logs
   - Check model path `/app/model/best.pt`
2. `blob_saved=false`
   - Check `BLOB_CONNECTION_STRING`
   - Check `aphid-images` permissions
3. `/history` returns 503
   - Check `BLOB_CONNECTION_STRING`
   - Check container `aphid-history`
4. `/telemetry` 401
   - If `IOT_API_KEY` is configured, send `X-API-Key`
5. `/telemetry` 503
   - Check `AZURE_STORAGE_CONNECTION_STRING` and `TELEMETRY_TABLE`
6. `/decision/weekly` always returns fallback source
   - Check `tepp_demo_model_enabled` and `tepp_demo_model_error` in `/health`
   - Ensure `scikit-learn` is installed and model file exists at `TEPP_DEMO_MODEL_PATH`
7. `/decision/weekly` always returns `scope_class=0`
   - Check `in_tepp_window` and `apps_so_far` in request
   - Compliance gate enforces window + max application count

## 10. Raspberry Pi Capture -> `/predict` Integration

The folder `third_party/PestInPeace_rashberrypi` is now wired to call this project's
YOLO API endpoint (`POST /predict`) instead of uploading images directly to Azure Blob.

### What changed

- `third_party/PestInPeace_rashberrypi/src/uploader.cpp`
  - Replaced Blob SAS upload with `curl -X POST ... -F image=@...` to `/predict`
  - Added runtime endpoint override via env var `PREDICT_URL`
- `third_party/PestInPeace_rashberrypi/include/uploader.hpp`
  - Function changed from `upload_to_azure(...)` to `upload_to_predict(...)`
- `third_party/PestInPeace_rashberrypi/src/camera.cpp`
  - Camera loop now sends each captured image to `/predict`

### Build and run on Raspberry Pi

```bash
cd third_party/PestInPeace_rashberrypi
export PREDICT_URL="https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict"
make clean && make
sudo ./iot_app
```

### Notes

- If `PREDICT_URL` is not set, a default URL is used in `src/uploader.cpp`.
- The `/predict` API already saves image/history in this project, so no extra Blob upload
  code is needed on the Raspberry Pi side.

