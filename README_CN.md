# PestinPeace - IoT 害虫监测系统

PestinPeace 是一套部署在 Azure 上的 IoT 害虫监测系统。它把树莓派/网页上传图片、YOLO 蚜虫与蛞蝓识别、Azure Table + Blob 存储、趋势预测、喷药决策、内置网页和 Grafana API 串在一起。

- 在线 API：`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`
- 文档总入口：`docs/README.md`
- 答辩资料包：`defense_assets/README_CN.md`

## 30 秒看懂架构

```text
树莓派 / 网页上传
  -> POST /predict
  -> YOLO 识别 aphid + slug
  -> Azure Blob 存图片/历史，Azure Table 存传感器/虫量/决策
  -> 网页、Grafana、趋势预测、forecast、decision 都通过 API 读取同一套数据
```

## 快速检查

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/health"
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/ready"
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/grafana/aphidcounts?device_id=demo-trap-001&limit=5"
```

图片识别：

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict?device_id=demo-trap-001&conf=0.25" \
  -F "image=@test.jpg"
```

`/predict` 关键返回字段：

- `aphid_count`：蚜虫数量，是趋势、预测和喷药决策的主输入。
- `slug_count`：蛞蝓数量，用于记录和展示。
- `total_count`：`aphid_count + slug_count`。
- `class_breakdown`：按类别统计的数量。
- `count`：兼容旧接口，等于 `aphid_count`。
- `count_mean`：兼容旧图表，当前单图模式下等于 `aphid_count`。
- `detections`：每个检测框，包含 `class_id`、`class_name`、置信度和 bbox。

## 当前业务逻辑

- 蚜虫是当前 forecast / decision 的主要决策信号。
- 蛞蝓是新增监测类别，先记录和展示，不直接触发喷药建议。
- 喷药决策使用 `aphid_count`，不是 `total_count`。
- 当前每次请求按单张图片记录：`images_in_round = 1`，`aggregation_mode = single_image`。

## 想做什么，看哪里

| 任务 | 文档 |
|---|---|
| 当前系统状态 | `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md` |
| 完整 API 说明 | `docs/API_REFERENCE.md` |
| Grafana 调用数据 | `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md` |
| 预测和决策逻辑 | `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md` |
| 模型更新 checklist | `docs/MODEL_UPDATE.md` |
| Slug 数据集说明 | `ml/yolo/SLUG_DATASET_NOTES_CN.md` |
| 环境变量 | `docs/ENV_VARS_REFERENCE.md` |
| 树莓派上传 | `docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md` |
| 树莓派本地决策 | `clients/raspberry_pi_decision/README.md` |
| 答辩材料 | `defense_assets/README_CN.md` |

## 内置页面入口

- `/predict/dashboard`
- `/telemetry/dashboard`
- `/history/dashboard`
- `/decision/dashboard`
- `/forecast/dashboard`

根 README 只保留入口信息。API 细节、部署、排障和答辩说明统一放在 `docs/`，避免多份文档互相漂移。
