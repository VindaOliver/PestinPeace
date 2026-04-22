# 当前部署摘要

## 当前正式环境

- Subscription: `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- Region: `swedencentral`
- Resource Group: `rg-aphid-yolo-payg`

## 当前线上地址

Base URL:

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 当前核心 Azure 资源

- Container App: `aca-aphid-yolo`
- Container Apps Environment: `aca-env-aphid-yolo`
- Container Registry: `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Log Analytics Workspace: `workspace-rgaphidyolopaygK1ST`

## 当前业务存储

### Azure Table

- `iottelemetry`
- `aphidcounts`

### Blob Containers

- `aphid-images`
- `aphid-history`

## 当前系统主链路

1. 用户上传虫子图片到 `/predict`
2. Raspberry Pi 上传传感器数据到 `/telemetry`
3. FastAPI 服务运行在 Azure Container App 中
4. 图片和历史记录写入 Blob
5. 传感器与虫量记录写入 Azure Table
6. Grafana 现在通过 API 读取：
   - `/grafana/telemetry`
   - `/grafana/aphidcounts`
7. GitHub Actions 自动把代码构建并部署到当前 PAYG 环境

## 当前答辩时最重要的说法

可以直接这样说：

> 我们已经把系统部署到 Azure PAYG 环境中，图像识别、环境采集、历史存储、预测与决策，以及 Grafana 数据读取接口都已经打通，并且代码变更可以通过 GitHub Actions 自动部署到线上环境。
