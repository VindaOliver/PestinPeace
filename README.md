# Aphid Detection Cloud Deployment Guide

This document is the handover guide for this project.
It explains what is deployed, how to run it, how to update to a better model, and how teammates can operate it safely.

---

## 1) Project Overview

This project trains a YOLO model for aphid detection and deploys inference to Azure Container Apps.

Main capabilities:
- Train a model locally (`train_yolo26.py`)
- Package trained `best.pt` into an inference container (`package_yolo26_container.py`)
- Deploy/update the service on Azure (`deploy_to_azure.ps1`)
- Call inference from browser (`local_web_client.html`)
- View admin-only history from browser (`admin_history_client.html`)
- Call inference from Raspberry Pi camera client (`raspberry_pi_client.py`)

Inference API endpoints:
- `GET /health`
- `POST /predict` (multipart image upload)
- `GET /admin/history` (admin-only, requires `X-Admin-Token`)

---

## 2) Current Live Deployment (as of 2026-02-12)

Subscription:
- `Azure for Students` (`12190bf7-b4d8-4dfa-9a63-01580c6ad868`)

Resource Group:
- `rg-aphid-yolo-se`

Region:
- `swedencentral`

Azure resources:
- Container App: `aca-aphid-yolo`
- Container App Environment: `aca-env-aphid-yolo`
- ACR: `acraphidyolo2498`

Current active revision:
- `aca-aphid-yolo--0000002` (`Running`, `Healthy`)

Public URLs:
- Health: `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health`
- Predict: `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict`

Current image tag:
- `aphid-yolo26:cors1`

Notes:
- CORS is enabled in the API (required for local browser calls).

---

## 3) Repository Files You Need

Core files:
- `train_yolo26.py` - training pipeline
- `continue_train_yolo26.py` - continue training pipeline
- `package_yolo26_container.py` - generates `.container_yolo26` (server + Dockerfile + model)
- `deploy_to_azure.ps1` - Azure deployment/update script
- `local_web_client.html` - local browser client for `/predict`
- `admin_history_client.html` - local browser admin history viewer
- `raspberry_pi_client.py` - camera capture + cloud inference client
- `.container_yolo26/` - generated Docker build context (regenerated each packaging run)

---

## 4) Local Prerequisites

Required:
- Python 3.9+ (project currently used Python 3.12 on Windows)
- Docker Desktop (Linux containers mode)
- Azure CLI
- Azure account access

Recommended:
- PowerShell

Install Azure CLI if needed:
```powershell
winget install --id Microsoft.AzureCLI -e --source winget
```

If `az` is not in PATH in current shell:
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" --version
```

Login:
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

---

## 5) Azure Policy/Region Constraints

This subscription has region restriction policy (`Allowed resource deployment regions`).

Allowed regions discovered during deployment:
- `swedencentral`
- `italynorth`
- `spaincentral`
- `switzerlandnorth`
- `norwayeast`

If deployment fails in another region (for example `eastus`), use one of the allowed regions above.

---

## 6) End-to-End Flow

1. Train model locally -> generate `best.pt`
2. Run packager -> create `.container_yolo26` with API server and model
3. Deploy script:
   - ensure resource group / ACR / Container Apps env
   - build and push image (ACR build or local Docker fallback)
   - create or update Container App
4. Validate `/health` and `/predict`
5. Share URL to browser or Raspberry Pi client

---

## 7) Initial Deployment (fresh or reproducible)

### 7.1 Generate container context from trained model
Default model path is auto-resolved if not found:
```powershell
python package_yolo26_container.py --no-build
```

Or specify model explicitly:
```powershell
python package_yolo26_container.py --model "runs/detect/runs/train/yolo26_aphid_count3/weights/best.pt" --no-build
```

### 7.2 Deploy to Azure
Use an allowed region:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:cors1 `
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" `
  -BlobImageContainer aphid-images `
  -BlobHistoryContainer aphid-history `
  -AdminToken "<SET_ADMIN_TOKEN>" `
  -UseLocalDockerBuild
```

Why `-UseLocalDockerBuild`:
- In this subscription, `az acr build` may be blocked (`TasksOperationsNotAllowed`), so local Docker build+push is the reliable path.

---

## 8) How to Deploy a Better Model (Model Upgrade Runbook)

Use this every time you have a better `best.pt`.

### Step A: train/continue training
Example:
```powershell
python train_yolo26.py --data data.yaml --model yolo26n.pt --epochs 100 --imgsz 640
```

Find latest model:
```powershell
Get-ChildItem -Path runs -Recurse -File -Filter best.pt | Sort-Object LastWriteTime -Descending | Select-Object -First 5 FullName,LastWriteTime
```

### Step B: package with new model
```powershell
python package_yolo26_container.py --model "<PATH_TO_NEW_BEST_PT>" --no-build
```

### Step C: deploy new image tag (do not reuse old tag)
Use semantic version tags for traceability (`v2026.02.12-1`, `v2`, etc.):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:v2026.02.12-2 `
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" `
  -BlobImageContainer aphid-images `
  -BlobHistoryContainer aphid-history `
  -AdminToken "<SET_ADMIN_TOKEN>" `
  -UseLocalDockerBuild
```

### Step D: verify
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

Predict test:
```powershell
python -c "import requests; f=open('data/val/images/Img_131.jpg','rb'); r=requests.post('https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict', files={'image':('Img_131.jpg', f, 'image/jpeg')}, timeout=120); print(r.status_code); print(r.text[:300])"
```

---

## 9) Rollback Procedure

If a new deployment is bad, redeploy previous known-good image tag:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:cors1 `
  -SkipAcrBuild
```

`-SkipAcrBuild` is safe if the target image already exists in ACR.

---

## 10) API Contract

Base URL:
- `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

### 10.1 `GET /health`
Response example:
```json
{
  "status": "ok",
  "model_path": "/app/model/best.pt"
}
```

Storage behavior:
- Each `/predict` request uploads the original image to Blob container `BLOB_CONTAINER_IMAGES`.
- Each `/predict` request writes a JSON history record to Blob container `BLOB_CONTAINER_HISTORY`.
- The response includes `request_id` and `blob_saved`.

### 10.3 `GET /admin/history`
Required header:
- `X-Admin-Token: <ADMIN_TOKEN>`

Query:
- `limit` (1-200, default 50)

Example:
```bash
curl -H "X-Admin-Token: <ADMIN_TOKEN>" \
  "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/admin/history?limit=20"
```

Response:
- Returns newest-first records from Blob history container.

### 10.2 `POST /predict`

Content-Type:
- `multipart/form-data`

Form field:
- `image` (file, required)

Query params (optional):
- `conf` (float, default `0.25`)
- `iou` (float, default `0.45`)
- `imgsz` (int, default `640`)
- `max_det` (int, default `1000`)

Example using `curl`:
```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

Response example:
```json
{
  "filename": "test.jpg",
  "count": 6,
  "detections": [
    {
      "class_id": 0,
      "class_name": "aphid",
      "confidence": 0.79,
      "bbox_xyxy": [645.5, 163.3, 723.2, 271.0]
    }
  ]
}
```

---

## 11) Local Browser Client Usage

File:
- `local_web_client.html`

Run local static server:
```powershell
python -m http.server 18090 --bind 127.0.0.1
```

Open:
- `http://127.0.0.1:18090/local_web_client.html`

If chosen port is occupied:
```powershell
netstat -ano | findstr :18090
```

Then switch to another free port (for example `18888`).

Admin page:
- `http://127.0.0.1:18090/admin_history_client.html`
- Fill endpoint + admin token, then load history.

Entra login admin page (no manual token):
- `http://127.0.0.1:18090/admin_history_entra.html`
- Fill `Tenant ID`, `Client ID`, `Scope`, then click `Sign In`.
- The page requests Entra access token and calls `/admin/history` with `Authorization: Bearer <token>`.

---

## 12) Raspberry Pi Client Usage

Install dependencies on Raspberry Pi:
```bash
pip install requests opencv-python
```

Run:
```bash
python raspberry_pi_client.py \
  --url https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io \
  --camera 0 \
  --interval 10 \
  --conf 0.25
```

Behavior:
- Captures image from camera
- Sends to cloud `/predict`
- Prints count + full JSON response

---

## 13) Operations and Diagnostics

### 13.1 Check revision health
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" containerapp revision list -g rg-aphid-yolo-se -n aca-aphid-yolo -o table
```

### 13.2 View app logs
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" containerapp logs show -g rg-aphid-yolo-se -n aca-aphid-yolo --tail 200
```

### 13.3 Common issues

1) `az` command not found  
Use full path:
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

2) `RequestDisallowedByAzure` region error  
Use allowed regions only (Section 5).

3) `TasksOperationsNotAllowed` in ACR build  
Deploy with `-UseLocalDockerBuild`.

4) Browser `Failed to fetch` (CORS)  
Ensure deployed image includes CORS middleware (current `cors1` does).

5) History not saved (`blob_saved=false`)  
Set these at deploy time:
- `BLOB_CONNECTION_STRING`
- `BLOB_CONTAINER_IMAGES`
- `BLOB_CONTAINER_HISTORY`
- `ADMIN_TOKEN`

6) `libxcb.so.1` missing in container  
Ensure Dockerfile contains required apt packages (`libxcb1`, `libgl1`, etc.), already handled by current packager.

7) Docker daemon not running  
Start Docker Desktop before deployment.

---

## 14) Security Notes

- Do not commit secrets, passwords, or credentials.
- `deploy_to_azure.ps1` uses ACR admin credentials at runtime; treat terminal history/logs as sensitive.
- Prefer moving to managed identity for production-grade security in future iterations.

---

## 15) Suggested Team Workflow

1. Model engineer trains and evaluates model.
2. Release owner chooses a new image tag and deploys.
3. QA verifies `/health` and `/predict` on fixed test images.
4. Team updates release log with:
   - model path/checkpoint
   - image tag
   - deployment timestamp
   - measured sample accuracy/latency

---

## 16) Quick Command Cheatsheet

Login:
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

Package latest model:
```powershell
python package_yolo26_container.py --no-build
```

Deploy new version:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 -ResourceGroup rg-aphid-yolo-se -Location swedencentral -RegistryName acraphidyolo2498 -ContainerEnvName aca-env-aphid-yolo -ContainerAppName aca-aphid-yolo -ImageName aphid-yolo26:vNEXT -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" -BlobImageContainer aphid-images -BlobHistoryContainer aphid-history -AdminToken "<SET_ADMIN_TOKEN>" -UseLocalDockerBuild
```

Deploy with Entra admin auth (recommended):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 -ResourceGroup rg-aphid-yolo-se -Location swedencentral -RegistryName acraphidyolo2498 -ContainerEnvName aca-env-aphid-yolo -ContainerAppName aca-aphid-yolo -ImageName aphid-yolo26:vENTRA -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" -BlobImageContainer aphid-images -BlobHistoryContainer aphid-history -EntraTenantId "<TENANT_ID>" -EntraClientId "<API_APP_CLIENT_ID>" -EntraAudience "api://<API_APP_CLIENT_ID>" -EntraAllowedGroupIds "<GROUP_OBJECT_ID_1>,<GROUP_OBJECT_ID_2>" -UseLocalDockerBuild
```

Check service:
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

## 17) GitHub Actions CI/CD

This repository now includes:
- `.github/workflows/deploy_containerapp.yml`

Full setup guide:
- `GITHUB_ACTIONS_SETUP.md`
