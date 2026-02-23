# PestinPeace (Azure YOLO + IoT)

This project provides:

1. YOLO image inference API for aphid detection (`/predict`)
2. IoT telemetry ingest/query APIs (`/telemetry`, `/telemetry/latest`)
3. Prediction history storage in Blob (`aphid-history`) with query API (`/history`)
4. Web pages for Predict / Monitor / History

## 1. Live Service

Base URL:

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

## 2. API Endpoints

### 2.1 Health

- `GET /health`

Example:

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

### 2.2 Predict (YOLO Inference)

- `POST /predict`
- Content type: `multipart/form-data`
- Required field: `image`
- Optional query params:
  - `conf` (default `0.25`)
  - `iou` (default `0.45`)
  - `imgsz` (default `640`)
  - `max_det` (default `1000`)

Example:

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

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
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d "{\"device_id\":\"pi-001\",\"temperature\":24.6,\"humidity\":58.2,\"light\":301}"
```

### 2.4 IoT Telemetry Query

- `GET /telemetry/latest?device_id=<id>&limit=<n>`
- `limit` default `100`, max `500`
- Optional header: `X-API-Key`

Example:

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry/latest?device_id=pi-001&limit=10"
```

### 2.5 Prediction History Query

- `GET /history?limit=<n>`
- Reads history JSON blobs from `aphid-history`
- `limit` default `50`, max `500`

Example:

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/history?limit=50"
```

### 2.6 Built-in Dashboards (Container App routes)

- Predict dashboard: `GET /predict/dashboard`
- Telemetry dashboard: `GET /telemetry/dashboard`
- History dashboard: `GET /history/dashboard`

## 3. Local Web Pages

Web pages are under:

- `web_pages/local_web_client.html` (Predict)
- `web_pages/telemetry_dashboard.html` (Monitor)
- `web_pages/history_records.html` (History)

Run local static server from repo root:

```bash
python -m http.server 18090
```

Open:

- `http://127.0.0.1:18090/web_pages/local_web_client.html`
- `http://127.0.0.1:18090/web_pages/telemetry_dashboard.html`
- `http://127.0.0.1:18090/web_pages/history_records.html`

Top navigation is linked across all three pages.

## 4. Azure Resources (Current)

Resource group: `rg-aphid-yolo-se`  
Region: `swedencentral`

Main resources:

- Container App: `aca-aphid-yolo`
- Container Apps Environment: `aca-env-aphid-yolo`
- Container Registry (ACR): `acraphidyolo2498`
- Storage Account: `staphid25021201`
- Log Analytics Workspace: `workspace-rgaphidyoloseNxBa`

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
2. Sync `web_pages/*.html` into `.container_yolo26/`
3. Build Docker image
4. Push image to ACR
5. Update Container App image
6. Health check

## 7. Update Model

1. Replace model:
   - `.container_yolo26/model/best.pt`
2. Commit and push:
   - `git add .`
   - `git commit -m "Update model"`
   - `git push origin main`
3. Wait for workflow success.
4. Verify `/health` and `/predict`.

## 8. Key Files

- `.container_yolo26/server.py`
- `.container_yolo26/Dockerfile`
- `.container_yolo26/requirements.txt`
- `.container_yolo26/model/best.pt`
- `web_pages/local_web_client.html`
- `web_pages/telemetry_dashboard.html`
- `web_pages/history_records.html`
- `package_yolo26_container.py`
- `deploy_to_azure.ps1`
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
