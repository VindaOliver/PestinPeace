# GitHub Actions -> ACR -> Azure Container Apps (PestinPeace)

Repository:

- `https://github.com/VindaOliver/PestinPeace`

Workflow file:

- `.github/workflows/deploy_containerapp.yml`

Pipeline behavior on push to `main`:

1. build Docker image from `apps/api/container`
2. push image to ACR
3. update Azure Container App image
4. call `/health` and `/decision/weekly` (smoke) to verify deployment

## 1. Required GitHub Variables

GitHub -> `Settings` -> `Secrets and variables` -> `Actions` -> `Variables`

Optional (workflow has built-in defaults):

- `ACR_NAME` (default: `acraphidyolo9547`)
- `RESOURCE_GROUP` (default: `rg-aphid-yolo-payg`)
- `CONTAINER_APP_NAME` (default: `aca-aphid-yolo`)
- `IMAGE_REPO` (default: `aphid-yolo26`)

## 2. Azure Login IDs for OIDC

GitHub -> `Settings` -> `Secrets and variables` -> `Actions` -> `Variables`

The workflow now has built-in defaults for:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

So these are optional. Best practice is still to set them explicitly as repository variables.

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
$SUB = "2685e946-e7eb-4d8a-ac8c-e899199ab4b3"
$SP_OBJECT_ID = "<OIDC_SERVICE_PRINCIPAL_OBJECT_ID>"

& $AZ role assignment create --assignee-object-id $SP_OBJECT_ID --assignee-principal-type ServicePrincipal --role AcrPush --scope "/subscriptions/$SUB/resourceGroups/rg-aphid-yolo-payg/providers/Microsoft.ContainerRegistry/registries/acraphidyolo9547"

& $AZ role assignment create --assignee-object-id $SP_OBJECT_ID --assignee-principal-type ServicePrincipal --role Contributor --scope "/subscriptions/$SUB/resourceGroups/rg-aphid-yolo-payg"
```

## 5. Deployment Trigger

- auto: push to `main`
- manual: GitHub -> `Actions` -> `Build Push Deploy (Container App)` -> `Run workflow`

## 6. Updating Model

Recommended:

1. regenerate container context:

```powershell
python scripts/deploy/package_yolo26_container.py --no-build
```

2. commit `apps/api/container/model/best.pt` and related files
3. push to `main`
4. wait for Actions to finish

## 7. Validation

After workflow succeeds, verify:

- `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/health`

## 8. Common Failures

- wrong Azure login IDs (client/tenant/subscription) -> `azure/login` fails
- no `AcrPush` role -> push to ACR denied
- no `Contributor` on RG -> `az containerapp update` denied
- model file missing in `apps/api/container/model/best.pt` -> workflow validation fails
