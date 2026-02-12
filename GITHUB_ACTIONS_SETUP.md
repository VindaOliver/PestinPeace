# GitHub Actions -> ACR -> Azure Container Apps (PestinPeace)

Repository:

- `https://github.com/VindaOliver/PestinPeace`

Workflow file:

- `.github/workflows/deploy_containerapp.yml`

Pipeline behavior on push to `main`:

1. build Docker image from `.container_yolo26`
2. push image to ACR
3. update Azure Container App image
4. call `/health` to verify deployment

## 1. Required GitHub Variables

GitHub -> `Settings` -> `Secrets and variables` -> `Actions` -> `Variables`

Required:

- `ACR_NAME` (current: `acraphidyolo2498`)
- `RESOURCE_GROUP` (current: `rg-aphid-yolo-se`)
- `CONTAINER_APP_NAME` (current: `aca-aphid-yolo`)

Optional:

- `IMAGE_REPO` (default: `aphid-yolo26`)

## 2. Required GitHub Secrets (OIDC)

GitHub -> `Settings` -> `Secrets and variables` -> `Actions` -> `Secrets`

Required:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## 3. Azure Side OIDC Setup

Create an Entra app (or reuse one) for GitHub Actions login.

Then add a federated credential:

- issuer: `https://token.actions.githubusercontent.com`
- subject: `repo:VindaOliver/PestinPeace:ref:refs/heads/main`
- audience: `api://AzureADTokenExchange`

## 4. Required Azure Role Assignments

Assign to the OIDC service principal:

- `AcrPush` on ACR scope
- `Contributor` on resource group scope

Example commands:

```powershell
$AZ = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
$SUB = "12190bf7-b4d8-4dfa-9a63-01580c6ad868"
$SP_OBJECT_ID = "<OIDC_SERVICE_PRINCIPAL_OBJECT_ID>"

& $AZ role assignment create --assignee-object-id $SP_OBJECT_ID --assignee-principal-type ServicePrincipal --role AcrPush --scope "/subscriptions/$SUB/resourceGroups/rg-aphid-yolo-se/providers/Microsoft.ContainerRegistry/registries/acraphidyolo2498"

& $AZ role assignment create --assignee-object-id $SP_OBJECT_ID --assignee-principal-type ServicePrincipal --role Contributor --scope "/subscriptions/$SUB/resourceGroups/rg-aphid-yolo-se"
```

## 5. Deployment Trigger

- auto: push to `main`
- manual: GitHub -> `Actions` -> `Build Push Deploy (Container App)` -> `Run workflow`

## 6. Updating Model

Recommended:

1. regenerate container context:

```powershell
python package_yolo26_container.py --no-build
```

2. commit `.container_yolo26/model/best.pt` and related files
3. push to `main`
4. wait for Actions to finish

## 7. Validation

After workflow succeeds, verify:

- `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health`

## 8. Common Failures

- missing repo variable/secret -> workflow fails early
- no `AcrPush` role -> push to ACR denied
- no `Contributor` on RG -> `az containerapp update` denied
- model file missing in `.container_yolo26/model/best.pt` -> workflow validation fails
