# GitHub Actions -> ACR -> Azure Container App

This repository includes a workflow at:

- `.github/workflows/deploy_containerapp.yml`

It does the following on every `push` to `main`:

1. Build Docker image from `.container_yolo26`
2. Push image to ACR
3. Update Azure Container App to new image
4. Call `/health` for verification

## 1) Prerequisites

- Azure Container App already exists
- Azure Container Registry (ACR) already exists
- `.container_yolo26/model/best.pt` exists in repo (or Git LFS)

## 2) Configure GitHub Repository Variables

In GitHub repo -> `Settings` -> `Secrets and variables` -> `Actions` -> `Variables`, add:

- `ACR_NAME` (example: `acraphidyolo2498`)
- `RESOURCE_GROUP` (example: `rg-aphid-yolo-se`)
- `CONTAINER_APP_NAME` (example: `aca-aphid-yolo`)
- `IMAGE_REPO` (optional, default: `aphid-yolo26`)

## 3) Configure GitHub Repository Secrets (OIDC mode)

Add these secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

These come from an Entra app/service principal configured for GitHub OIDC.

## 4) Azure Role Assignments for the OIDC Principal

Assign roles to the service principal:

- `AcrPush` on ACR scope
- `Contributor` on the Container App resource group

You may replace `Contributor` with a narrower custom role if desired.

## 5) Create Federated Credential (GitHub OIDC)

In Entra App -> `Federated credentials`, create one for your repository:

- Issuer: `https://token.actions.githubusercontent.com`
- Subject example: `repo:<owner>/<repo>:ref:refs/heads/main`
- Audience: `api://AzureADTokenExchange`

## 6) Model Update Workflow

When a better model is available:

1. Regenerate container context locally:
   - `python package_yolo26_container.py --no-build`
2. Commit updated files (especially `.container_yolo26/model/best.pt`)
3. Push to `main`
4. GitHub Actions deploys automatically

## 7) Manual Trigger

You can also run workflow manually:

- GitHub -> `Actions` -> `Build Push Deploy (Container App)` -> `Run workflow`

## 8) Notes

- If model file is large, use Git LFS.
- If `/health` step fails, inspect workflow logs and Azure Container App logs.
- Workflow always deploys a SHA-tag image and also updates `latest`.
