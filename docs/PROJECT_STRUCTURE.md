# Project Structure

This repository is organized using an app-first layout:

```text
apps/
  api/
    container/        # FastAPI service, Docker context, runtime models
  web/
    web_pages/        # Static dashboards
clients/
  raspberry_pi/       # Device-side Python client
ml/
  yolo/               # YOLO training scripts/config/weights
  tepp/               # Teppeki demo training script
scripts/
  deploy/             # Packaging and Azure deployment scripts
docs/                 # Operational and usage docs
third_party/          # External/vendor code
```

## Operational Entry Points

- CI workflow: `.github/workflows/deploy_containerapp.yml`
- Local Azure deployment script: `scripts/deploy/deploy_to_azure.ps1`
- Container packaging helper: `scripts/deploy/package_yolo26_container.py`
- API runtime code: `apps/api/container/server.py`
- Static web pages: `apps/web/web_pages/*.html`
