param(
    [string]$ResourceGroup = "rg-aphid-yolo-payg",
    [string]$WorkspaceName = "workspace-rgaphidyolopaygK1ST",
    [string]$StorageAccountName = "staphidpayg9547",
    [string]$Location = "swedencentral",
    [string]$DataCollectionRuleName = "dcr-azure-table-sync",
    [string]$GitHubOidcClientId = "411ad807-be68-4d9c-bbe2-d99cfc655c4d"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$templatePath = Join-Path $repoRoot "infra\azure\log_analytics_table_sync_dcr.template.json"

Write-Host "Creating Log Analytics custom tables..."
az monitor log-analytics workspace table show `
  --resource-group $ResourceGroup `
  --workspace-name $WorkspaceName `
  --name IoTTelemetry_CL `
  --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    az monitor log-analytics workspace table create `
      --resource-group $ResourceGroup `
      --workspace-name $WorkspaceName `
      --name IoTTelemetry_CL `
      --columns TimeGenerated=datetime PartitionKey=string RowKey=string DeviceId=string Ts=datetime Temperature=real Humidity=real PressureHpa=real Light=real CreatedAt=datetime `
      --output none
}

az monitor log-analytics workspace table show `
  --resource-group $ResourceGroup `
  --workspace-name $WorkspaceName `
  --name AphidCounts_CL `
  --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    az monitor log-analytics workspace table create `
      --resource-group $ResourceGroup `
      --workspace-name $WorkspaceName `
      --name AphidCounts_CL `
      --columns TimeGenerated=datetime PartitionKey=string RowKey=string DeviceId=string SourceDeviceId=string RequestId=string Ts=datetime Filename=string Count=int ImageBlobName=string HistoryBlobName=string CreatedAt=datetime `
      --output none
}

$workspaceId = az monitor log-analytics workspace show `
  --resource-group $ResourceGroup `
  --workspace-name $WorkspaceName `
  --query id `
  --output tsv

Write-Host "Deploying DCR..."
az deployment group create `
  --resource-group $ResourceGroup `
  --template-file $templatePath `
  --parameters dataCollectionRuleName=$DataCollectionRuleName location=$Location workspaceResourceId=$workspaceId `
  --output none

$dcrId = az monitor data-collection rule show `
  --resource-group $ResourceGroup `
  --name $DataCollectionRuleName `
  --query id `
  --output tsv

$githubSpObjectId = az ad sp show --id $GitHubOidcClientId --query id --output tsv
if ($githubSpObjectId) {
    $existingAssignment = az role assignment list `
      --assignee-object-id $githubSpObjectId `
      --scope $dcrId `
      --query "[?roleDefinitionName=='Monitoring Metrics Publisher'] | [0].id" `
      --output tsv

    if (-not $existingAssignment) {
        Write-Host "Assigning Monitoring Metrics Publisher to GitHub OIDC service principal..."
        az role assignment create `
          --assignee-object-id $githubSpObjectId `
          --assignee-principal-type ServicePrincipal `
          --role "Monitoring Metrics Publisher" `
          --scope $dcrId `
          --output none
    }
}

Write-Host "Done. DCR ID: $dcrId"
Write-Host "Use 'az monitor data-collection rule show --resource-group $ResourceGroup --name $DataCollectionRuleName' to inspect immutableId and ingestion endpoint."
