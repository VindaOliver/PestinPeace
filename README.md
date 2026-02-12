# PestinPeace

PestinPeace is an aphid detection and counting project using a YOLO model, deployed on Azure Container Apps.

Current repository: `https://github.com/VindaOliver/PestinPeace`

## 1. Current Status

This repository now supports:

- Cloud inference API on Azure Container App
- Image + history storage to Azure Blob
- Admin history access with Entra login (recommended)
- Local web clients for prediction and admin review
- GitHub Actions pipeline: build -> push to ACR -> update Container App

## 2. Architecture

- Inference container (FastAPI + Ultralytics YOLO)
- Azure Blob Storage:
  - image container for uploaded images
  - history container for JSON records
- Azure Container App endpoint
- Local clients:
  - `local_web_client.html` for prediction
  - `admin_history_entra.html` for admin history

## 3. API Endpoints

Base URL (current deployment):

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

### `GET /health`

Returns runtime status and auth mode.

### `POST /predict`

- `multipart/form-data`
- required file field: `image`
- optional query params: `conf`, `iou`, `imgsz`, `max_det`

Response includes:

- `request_id`
- `count`
- `detections`
- `blob_saved`

### `GET /admin/history`

Admin-only endpoint.

Auth behavior:

- Entra mode enabled: requires `Authorization: Bearer <token>`
- Fallback token mode: `X-Admin-Token` (only if Entra is not enabled)

## 4. Auth (Current)

Current deployment is configured for Entra admin authentication.

Container app env vars used by auth:

- `ENTRA_TENANT_ID`
- `ENTRA_CLIENT_ID`
- `ENTRA_AUDIENCE` (optional)
- `ENTRA_ALLOWED_GROUP_IDS` (optional)
- `ENTRA_ALLOWED_USER_OBJECT_IDS` (optional)
- `ENTRA_ALLOWED_ROLES` (optional)

## 5. Local Clients

## 5.1 Prediction page

- file: `local_web_client.html`
- run local static host:

```powershell
python -m http.server 18090 --bind 127.0.0.1
```

- open:

`http://127.0.0.1:18090/local_web_client.html`

## 5.2 Admin Entra page

- file: `admin_history_entra.html`
- open:

`http://127.0.0.1:18090/admin_history_entra.html`

Fill:

- API base URL
- Tenant ID
- Client ID (SPA app)
- Scope (optional; can be blank for idToken mode)

Then:

- click `Sign In`
- click `Load History`

## 6. Deployment Scripts

### 6.1 Build context

```powershell
python package_yolo26_container.py --no-build
```

### 6.2 Deploy to Azure

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 \
  -ResourceGroup rg-aphid-yolo-se \
  -Location swedencentral \
  -RegistryName acraphidyolo2498 \
  -ContainerEnvName aca-env-aphid-yolo \
  -ContainerAppName aca-aphid-yolo \
  -ImageName aphid-yolo26:vNEXT \
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" \
  -BlobImageContainer aphid-images \
  -BlobHistoryContainer aphid-history \
  -EntraTenantId "<TENANT_ID>" \
  -EntraClientId "<CLIENT_ID>" \
  -EntraAllowedUserObjectIds "<USER_OBJECT_ID>" \
  -UseLocalDockerBuild
```

## 7. GitHub Actions CI/CD

Workflow:

- `.github/workflows/deploy_containerapp.yml`

On push to `main`, it will:

1. build Docker image from `.container_yolo26`
2. push to ACR
3. update Container App image
4. run `/health` check

Setup guide:

- `GITHUB_ACTIONS_SETUP.md`

## 8. Updating to a Better Model

Recommended process:

1. replace model and regenerate context:

```powershell
python package_yolo26_container.py --no-build
```

2. commit and push to `main`
3. GitHub Actions deploys automatically
4. validate `/health` and sample `/predict`

## 9. Repository Scope

This repository is intentionally deployment-focused.

Not included in git:

- training datasets (`data/`)
- training outputs (`runs/`)
- local training scripts and local pretrained file (ignored for cleaner collaboration)

## 10. Troubleshooting

### `msal is not defined`

`admin_history_entra.html` now tries multiple script sources and local fallback (`./vendor/msal-browser.min.js`).

### `AADSTS9002326`

Entra app must use `spa.redirectUris` for browser login, not `web.redirectUris`.

### `blob_saved=false`

Check:

- `BLOB_CONNECTION_STRING`
- `BLOB_CONTAINER_IMAGES`
- `BLOB_CONTAINER_HISTORY`

### Port occupied locally

Use another port:

```powershell
python -m http.server 18888 --bind 127.0.0.1
```

## 11. Security Notes

- Do not commit secrets.
- Use Entra + OIDC for production flows.
- Rotate any previously exposed tokens/keys.
