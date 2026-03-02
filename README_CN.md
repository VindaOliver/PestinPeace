# PestinPeace（Azure YOLO + IoT）

本项目提供以下能力：

1. 蚜虫图像检测 API（`/predict`）
2. IoT 遥测写入与查询 API（`/telemetry`, `/telemetry/latest`）
3. 检测历史写入 Blob（`aphid-history`）并支持查询（`/history`）
4. 前端页面（检测 / 监控 / 历史）
5. 周级喷施范围 demo 决策 API（`/decision/weekly`）

## 1. 在线服务

Base URL：

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

## 2. API 说明

### 2.1 健康检查

- `GET /health`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

### 2.2 YOLO 图像检测

- `POST /predict`
- Content-Type: `multipart/form-data`
- 必填字段：`image`
- 可选 query 参数：
  - `conf`（默认 `0.25`）
  - `iou`（默认 `0.45`）
  - `imgsz`（默认 `640`）
  - `max_det`（默认 `1000`）

示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

### 2.3 遥测上传

- `POST /telemetry`
- Content-Type: `application/json`
- 字段：
  - `device_id`（必填）
  - `temperature`（可选）
  - `humidity`（可选）
  - `light`（可选）
  - `ts`（可选，ISO 时间）
- 可选请求头：
  - `X-API-Key`（仅当配置 `IOT_API_KEY` 时必填）

示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d "{\"device_id\":\"pi-001\",\"temperature\":24.6,\"humidity\":58.2,\"light\":301}"
```

### 2.4 遥测查询

- `GET /telemetry/latest?device_id=<id>&limit=<n>`
- `limit` 默认 `100`，最大 `500`
- 可选请求头：`X-API-Key`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry/latest?device_id=pi-001&limit=10"
```

### 2.5 历史查询

- `GET /history?limit=<n>`
- 从 Blob 容器 `aphid-history` 读取历史 JSON
- `limit` 默认 `50`，最大 `500`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/history?limit=50"
```

### 2.6 内置页面路由

- 检测页：`GET /predict/dashboard`
- 监控页：`GET /telemetry/dashboard`
- 历史页：`GET /history/dashboard`

### 2.7 周级喷施决策（Demo）

- `POST /decision/weekly`
- Content-Type: `application/json`
- 必填字段：
  - `aphid_count`
  - `field_area_ha`
- 可选字段：
  - `exposure_days`（默认 `7`）
  - `week_start`（`YYYY-MM-DD`，用于季节编码与窗口推断）
  - `prev_catch_rate` 或 `catch_trend`
  - `t_mean`, `rh_mean`, `vpd_mean`
  - `in_tepp_window`（`0/1`，不传则按日期推断）
  - `apps_so_far`（默认 `0`）
  - `respect_compliance_gate`（默认 `true`）

示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/decision/weekly" \
  -H "Content-Type: application/json" \
  -d "{\"aphid_count\":18,\"field_area_ha\":2.0,\"exposure_days\":7,\"t_mean\":16.4,\"rh_mean\":72,\"apps_so_far\":0}"
```

## 3. 项目结构（工业化分层）

- `apps/api/container/`：FastAPI 服务、Dockerfile、运行模型文件
- `apps/web/web_pages/`：静态页面（检测 / 监控 / 历史）
- `ml/yolo/`：YOLO 训练脚本、配置、基础权重
- `ml/tepp/`：周级决策 demo 模型训练脚本
- `scripts/deploy/`：打包与部署脚本
- `clients/raspberry_pi/`：设备端 Python 客户端
- `docs/`：部署与模型使用文档
- `third_party/`：外部代码

详细结构说明见：`docs/PROJECT_STRUCTURE.md`。

## 4. 本地页面

页面文件：

- `apps/web/web_pages/local_web_client.html`
- `apps/web/web_pages/telemetry_dashboard.html`
- `apps/web/web_pages/history_records.html`

在仓库根目录启动静态服务：

```bash
python -m http.server 18090
```

访问：

- `http://127.0.0.1:18090/apps/web/web_pages/local_web_client.html`
- `http://127.0.0.1:18090/apps/web/web_pages/telemetry_dashboard.html`
- `http://127.0.0.1:18090/apps/web/web_pages/history_records.html`

## 5. 模型更新

1. 替换 YOLO 权重：
   - `apps/api/container/model/best.pt`
2. 可选：放入决策模型文件（用于 `/decision/weekly` 的模型模式）：
   - `apps/api/container/model/tepp_demo_scope_model.pkl`
   - `apps/api/container/model/tepp_demo_meta.json`
3. 提交并推送：
   - `git add .`
   - `git commit -m "Update model"`
   - `git push origin main`
4. 等待 GitHub Actions 完成部署。
5. 验证 `/health`、`/predict`、`/decision/weekly`。

## 6. 关键文件

- `apps/api/container/server.py`
- `apps/api/container/Dockerfile`
- `apps/api/container/requirements.txt`
- `apps/api/container/model/best.pt`
- `apps/api/container/model/tepp_demo_scope_model.pkl`（可选）
- `apps/api/container/model/tepp_demo_meta.json`（可选）
- `apps/web/web_pages/local_web_client.html`
- `apps/web/web_pages/telemetry_dashboard.html`
- `apps/web/web_pages/history_records.html`
- `scripts/deploy/package_yolo26_container.py`
- `scripts/deploy/deploy_to_azure.ps1`
- `.github/workflows/deploy_containerapp.yml`

## 7. 排障

1. `/predict` 异常
   - 看 Container App 日志
   - 检查模型路径 `/app/model/best.pt`
2. `blob_saved=false`
   - 检查 `BLOB_CONNECTION_STRING`
   - 检查 `aphid-images` 容器权限
3. `/history` 返回 503
   - 检查 `BLOB_CONNECTION_STRING`
   - 检查 `aphid-history` 容器
4. `/telemetry` 返回 401
   - 若配置了 `IOT_API_KEY`，必须带 `X-API-Key`
5. `/telemetry` 返回 503
   - 检查 `AZURE_STORAGE_CONNECTION_STRING` 与 `TELEMETRY_TABLE`
6. `/decision/weekly` 总是 fallback
   - 查看 `/health` 里的 `tepp_demo_model_enabled` 和 `tepp_demo_model_error`
   - 检查 `TEPP_DEMO_MODEL_PATH` 指向的 `.pkl` 是否存在，且镜像内已安装 `scikit-learn`
7. `/decision/weekly` 总是 `scope_class=0`
   - 检查请求中的 `in_tepp_window` 与 `apps_so_far`
   - 合规门控默认开启，会强制执行窗口与次数约束
