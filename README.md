# PestinPeace Inference Service

This repository provides a YOLO-based aphid detection API deployed on Azure Container Apps.

## Current API

Base URL:

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

Endpoints:

- `GET /health`
- `POST /predict`

There is no admin endpoint and no history API in the current version.

## Predict Request

`POST /predict` uses `multipart/form-data`:

- field: `image` (required)
- query params (optional):
  - `conf` (default `0.25`)
  - `iou` (default `0.45`)
  - `imgsz` (default `640`)
  - `max_det` (default `1000`)

Example:

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

## Blob Storage Behavior

If Blob is configured, each `/predict` call uploads the input image to:

- container: `aphid-images`

No history JSON is written by the API.

## Local Web Client

Start a static server from repo root:

```bash
python -m http.server 18090
```

Open:

`http://127.0.0.1:18090/local_web_client.html`

## Deploy New Model (GitHub Actions + ACR)

1. Replace model file:
   - `.container_yolo26/model/best.pt`
2. (Optional) Regenerate container context:
   - `python package_yolo26_container.py --no-build`
3. Commit and push to `main`:
   - `git add .container_yolo26`
   - `git commit -m "Update model"`
   - `git push origin main`

Push to `main` triggers workflow:

- Docker build
- Push image to ACR
- Update Azure Container App image

## Key Files

- `.container_yolo26/server.py`: runtime API server
- `.container_yolo26/model/best.pt`: deployed model
- `.github/workflows/deploy_containerapp.yml`: CI/CD pipeline
- `package_yolo26_container.py`: generates `.container_yolo26` context
