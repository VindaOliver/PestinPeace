# Docs Guide

这份文件是当前 `docs/` 目录的入口页。
目标很简单：告诉大家先看哪份，不要再去翻旧学生订阅阶段留下来的过渡文档。

## Recommended Reading Order

如果你只想最快接手当前系统，按这个顺序看：

1. `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
   - 适合之前一直在用旧学生订阅的人
   - 说明现在已经切到哪个 PAYG 环境，哪些地址和资源名变了

2. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
   - 适合理解整套系统怎么工作的同学
   - 重点是识别、传感器、预测、决策、部署和线上入口

3. `docs/GITHUB_ACTIONS_SETUP.md`
   - 适合负责部署和运维的人
   - 重点是 GitHub Actions -> ACR -> Container App 这条自动部署链路

4. `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
   - 适合负责 Grafana 接入和查数据的人
   - 这是当前 PAYG 订阅下的有效版本

5. `docs/GRAFANA_TEAMMATE_STEPS_1_2_5_6_CN.md`
   - 适合负责 Grafana 第 1、2、5、6 步的同学
   - 重点是怎么进 Grafana、怎么配 Azure Monitor、怎么 Save & Test

6. `docs/LOG_ANALYTICS_TABLE_SYNC_CN.md`
   - 适合负责把业务表同步进 Log Analytics 的人
   - 说明 `iottelemetry` / `aphidcounts` 如何变成 `IoTTelemetry_CL` / `AphidCounts_CL`

## Current Docs

### Deployment And Environment

- `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
- `docs/GITHUB_ACTIONS_SETUP.md`
- `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
- `docs/GRAFANA_TEAMMATE_STEPS_1_2_5_6_CN.md`
- `docs/LOG_ANALYTICS_TABLE_SYNC_CN.md`

### Business Flow And APIs

- `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
- `docs/APHID_FORECAST_API_USAGE.md`
- `docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`
- `docs/TEPP_DEMO_MODEL_USAGE.md`

### Project Structure

- `docs/PROJECT_STRUCTURE.md`

## Read By Role

### 如果你是旧学生订阅的使用者

先看：

`docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`

### 如果你是开发或维护同学

先看：

1. `docs/PROJECT_STRUCTURE.md`
2. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
3. `docs/GITHUB_ACTIONS_SETUP.md`

### 如果你只负责 Grafana

先看：

1. `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
2. `docs/GRAFANA_TEAMMATE_STEPS_1_2_5_6_CN.md`
3. `docs/LOG_ANALYTICS_TABLE_SYNC_CN.md`

### 如果你只负责树莓派或传感器上传

先看：

`docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`

## Principle

现在 `docs/` 目录只保留两类东西：

- 当前 PAYG 环境下还有效的说明
- 对 teammate 接手和协作真正有帮助的文档

一句话说：

```text
现在 docs/ 里保留的是“当前有效版本”，
不是把所有历史讨论都继续堆着不动。
```
