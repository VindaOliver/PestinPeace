[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-aphid-yolo",
    [string]$Location = "eastus",
    [string]$RegistryName = ("acraphidyolo" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ContainerEnvName = "aca-env-aphid-yolo",
    [string]$ContainerAppName = ("aca-aphid-yolo-" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ImageName = "aphid-yolo26:latest",
    [string]$ContextDir = ".container_yolo26",
    [double]$Cpu = 2.0,
    [string]$Memory = "4Gi",
    [int]$MinReplicas = 1,
    [int]$MaxReplicas = 3,
    [string]$BlobConnectionString = "",
    [string]$BlobImageContainer = "aphid-images",
    [switch]$UseLocalDockerBuild,
    [switch]$SkipAcrBuild
)

$ErrorActionPreference = "Stop"

function Resolve-AzExecutable() {
    $azCmd = Get-Command az -ErrorAction SilentlyContinue
    if ($azCmd) {
        return $azCmd.Source
    }

    $candidates = @(
        "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        "C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) {
            return $p
        }
    }

    throw "Azure CLI not found. Install with: winget install --id Microsoft.AzureCLI -e --source winget"
}

function Invoke-Az([string]$CommandText) {
    Write-Host ">> az $CommandText"
    Invoke-Expression "& `"$script:AzExe`" $CommandText"
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $CommandText"
    }
}

function Invoke-LocalDockerBuildPush([string]$ImageRef, [string]$RegistryName, [string]$ContextDir) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI not found. Install Docker Desktop or remove -UseLocalDockerBuild."
    }

    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not running. Start Docker Desktop and rerun."
    }

    Write-Host ">> docker build --platform linux/amd64 -t $ImageRef $ContextDir"
    docker build --platform linux/amd64 -t $ImageRef $ContextDir
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed."
    }

    Invoke-Az "acr login --name $RegistryName --only-show-errors"

    Write-Host ">> docker push $ImageRef"
    docker push $ImageRef
    if ($LASTEXITCODE -ne 0) {
        throw "Docker push failed."
    }
}

$script:AzExe = Resolve-AzExecutable
Write-Host "Using Azure CLI: $script:AzExe"

try {
    Invoke-Expression "& `"$script:AzExe`" account show --only-show-errors" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Please run: az login"
    }
} catch {
    throw "Azure login is required. Run 'az login' first."
}

if (-not (Test-Path -LiteralPath $ContextDir)) {
    throw "Container context directory not found: $ContextDir"
}

Write-Host "Deployment configuration:"
Write-Host "  ResourceGroup:    $ResourceGroup"
Write-Host "  Location:         $Location"
Write-Host "  RegistryName:     $RegistryName"
Write-Host "  ContainerEnvName: $ContainerEnvName"
Write-Host "  ContainerAppName: $ContainerAppName"
Write-Host "  ImageName:        $ImageName"
Write-Host "  ContextDir:       $ContextDir"
Write-Host "  BlobEnabled:      $([bool]$BlobConnectionString)"

Invoke-Az "group create -n $ResourceGroup -l $Location --only-show-errors"
Invoke-Az "provider register --namespace Microsoft.ContainerRegistry --wait --only-show-errors"

$acrCount = Invoke-Expression "& `"$script:AzExe`" acr list -g $ResourceGroup --query `"[?name=='$RegistryName'] | length(@)`" -o tsv"
if ([int]$acrCount -eq 0) {
    Invoke-Az "acr create -g $ResourceGroup -n $RegistryName --sku Basic --admin-enabled true --only-show-errors"
} else {
    Write-Host ">> ACR exists: $RegistryName"
}

$imageRef = "$RegistryName.azurecr.io/$ImageName"

if (-not $SkipAcrBuild) {
    if ($UseLocalDockerBuild) {
        Invoke-LocalDockerBuildPush -ImageRef $imageRef -RegistryName $RegistryName -ContextDir $ContextDir
    } else {
        try {
            Invoke-Az "acr build --registry $RegistryName --image $ImageName $ContextDir --only-show-errors"
        } catch {
            Write-Host ">> ACR build failed, falling back to local Docker build/push."
            Invoke-LocalDockerBuildPush -ImageRef $imageRef -RegistryName $RegistryName -ContextDir $ContextDir
        }
    }
} else {
    Write-Host ">> Skip ACR build as requested."
}

Invoke-Az "extension add --name containerapp --upgrade --only-show-errors"
Invoke-Az "provider register --namespace Microsoft.App --wait --only-show-errors"
Invoke-Az "provider register --namespace Microsoft.OperationalInsights --wait --only-show-errors"

$envCount = Invoke-Expression "& `"$script:AzExe`" containerapp env list -g $ResourceGroup --query `"[?name=='$ContainerEnvName'] | length(@)`" -o tsv"
if ([int]$envCount -eq 0) {
    Invoke-Az "containerapp env create -g $ResourceGroup -n $ContainerEnvName -l $Location --only-show-errors"
} else {
    Write-Host ">> Container Apps environment exists: $ContainerEnvName"
}

$acrUser = Invoke-Expression "& `"$script:AzExe`" acr credential show -n $RegistryName --query `"username`" -o tsv"
$acrPass = Invoke-Expression "& `"$script:AzExe`" acr credential show -n $RegistryName --query `"passwords[0].value`" -o tsv"
if (-not $acrUser -or -not $acrPass) {
    throw "Failed to read ACR credentials for registry: $RegistryName"
}

$envVars = @(
    "MODEL_PATH=/app/model/best.pt",
    "BLOB_CONTAINER_IMAGES=$BlobImageContainer"
)
$secretPairs = @()
if ($BlobConnectionString) {
    $secretPairs += "blob-conn='$BlobConnectionString'"
    $envVars += "BLOB_CONNECTION_STRING=secretref:blob-conn"
}
$envVarsArg = ($envVars -join " ")
$secretArg = ""
if ($secretPairs.Count -gt 0) {
    $secretArg = " --secrets " + ($secretPairs -join " ")
}

$appCount = Invoke-Expression "& `"$script:AzExe`" containerapp list -g $ResourceGroup --query `"[?name=='$ContainerAppName'] | length(@)`" -o tsv"
if ([int]$appCount -eq 0) {
    $createCmd = "containerapp create -g $ResourceGroup -n $ContainerAppName --environment $ContainerEnvName --image $imageRef --ingress external --target-port 8000 --registry-server $RegistryName.azurecr.io --registry-username $acrUser --registry-password $acrPass --cpu $Cpu --memory $Memory --min-replicas $MinReplicas --max-replicas $MaxReplicas$secretArg --env-vars $envVarsArg --only-show-errors"
    Invoke-Az $createCmd
} else {
    Write-Host ">> Container App exists, updating image and scale settings."
    Invoke-Az "containerapp registry set -g $ResourceGroup -n $ContainerAppName --server $RegistryName.azurecr.io --username $acrUser --password $acrPass --only-show-errors"
    if ($secretPairs.Count -gt 0) {
        $secretSetCmd = "containerapp secret set -g $ResourceGroup -n $ContainerAppName --secrets " + ($secretPairs -join " ") + " --only-show-errors"
        Invoke-Az $secretSetCmd
    }
    $updateCmd = "containerapp update -g $ResourceGroup -n $ContainerAppName --image $imageRef --cpu $Cpu --memory $Memory --min-replicas $MinReplicas --max-replicas $MaxReplicas --set-env-vars $envVarsArg --only-show-errors"
    Invoke-Az $updateCmd
}

$fqdn = Invoke-Expression "& `"$script:AzExe`" containerapp show -g $ResourceGroup -n $ContainerAppName --query `"properties.configuration.ingress.fqdn`" -o tsv"
if (-not $fqdn) {
    throw "Deployment completed but failed to resolve app FQDN."
}

Write-Host ""
Write-Host "Deployment completed."
Write-Host "Health URL:  https://$fqdn/health"
Write-Host "Predict URL: https://$fqdn/predict"
