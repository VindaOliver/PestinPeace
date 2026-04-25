# Docs Guide

这份文件是当前 `docs/` 目录的总入口。
目标很简单：告诉大家现在这套系统该先看哪份文档，不再去翻旧思路或过渡材料。

## 先看这 5 份

如果你时间不多，只看下面这 5 份就够了：

1. `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
2. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
3. `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
4. `docs/API_REFERENCE.md`
5. `docs/GITHUB_ACTIONS_SETUP.md`

如果你正在准备答辩，再加看：

6. `docs/AZURE_ARCHITECTURE_DEFENSE_CN.md`
7. `docs/DUAL_CLASS_INTEGRATION_REPORT_CN.md`
8. `defense_assets/README_CN.md`

## 按角色看

### 1. 项目负责人 / 答辩准备

先看：

1. `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
2. `docs/AZURE_ARCHITECTURE_DEFENSE_CN.md`
3. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
4. `docs/DUAL_CLASS_INTEGRATION_REPORT_CN.md`
5. `ml/yolo/SLUG_DATASET_NOTES_CN.md`

### 2. 接手部署和维护的同学

先看：

1. `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
2. `docs/GITHUB_ACTIONS_SETUP.md`
3. `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
4. `docs/MODEL_UPDATE.md`
5. `docs/ENV_VARS_REFERENCE.md`
6. `docs/PROJECT_STRUCTURE.md`

### 3. 负责 Grafana 的同学

先看：

1. `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
2. `docs/GRAFANA_API_DATASOURCE_QUICKSTART_CN.md`

说明：

- 现在 Grafana 读取业务数据走 API，不再走旧的 Log Analytics 业务同步方案。
- 主要接口是：
  - `/grafana/telemetry`
  - `/grafana/aphidcounts`
  - `/grafana/decisionhistory`

### 4. 负责树莓派 / 传感器上传的同学

先看：

1. `docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`
2. `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
3. `clients/raspberry_pi_decision/README.md`

### 5. 负责预测和决策逻辑的同学

先看：

1. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
2. `docs/APHID_FORECAST_API_USAGE.md`
3. `docs/TEPP_DEMO_MODEL_USAGE.md`
4. `docs/API_REFERENCE.md`

## 当前有效文档清单

### 系统状态与交接

- `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
- `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
- `docs/DUAL_CLASS_INTEGRATION_REPORT_CN.md`

### 部署与环境

- `docs/GITHUB_ACTIONS_SETUP.md`
- `docs/AZURE_ARCHITECTURE_DEFENSE_CN.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/MODEL_UPDATE.md`
- `docs/ENV_VARS_REFERENCE.md`

### 业务流程与 API

- `docs/API_REFERENCE.md`
- `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
- `docs/APHID_FORECAST_API_USAGE.md`
- `docs/TEPP_DEMO_MODEL_USAGE.md`
- `docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`
- `clients/raspberry_pi_decision/README.md`

### Grafana

- `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
- `docs/GRAFANA_API_DATASOURCE_QUICKSTART_CN.md`

### 答辩素材

- `defense_assets/README_CN.md`
- `docs/AZURE_ARCHITECTURE_DEFENSE_CN.md`
- `ml/yolo/SLUG_DATASET_NOTES_CN.md`

## 现在这套系统的主线

当前正式运行的是 Azure PAYG 环境，主线是：

- GitHub `main` 分支触发 GitHub Actions
- GitHub Actions 自动部署到 Azure Container App
- 业务数据通过 API 读取
- Grafana 通过 API 看业务数据

当前最关键的线上入口是：

- Base URL:
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 文档整理原则

现在 `docs/` 目录只保留两类东西：

- 当前 PAYG 环境下仍然有效的说明
- 对 teammate 接手、协作、答辩真正有帮助的文档

如果后面要继续精简，优先删“重复说明”，不要删“主入口文档”。
