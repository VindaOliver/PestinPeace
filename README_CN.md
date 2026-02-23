# PestinPeace 项目说明（中文）

本项目提供三类能力：

1. 蚜虫图片识别（`/predict`）
2. IoT 传感器数据上报与查询（`/telemetry`、`/telemetry/latest`）
3. 识别历史记录存储与查询（`/history`，数据存到 Blob `aphid-history`）

## 1. 线上服务地址

基础地址：

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

## 2. 接口说明

### 2.1 健康检查

- `GET /health`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

### 2.2 预测接口（YOLO）

- `POST /predict`
- 请求类型：`multipart/form-data`
- 必填字段：`image`
- 可选参数：
  - `conf`（默认 `0.25`）
  - `iou`（默认 `0.45`）
  - `imgsz`（默认 `640`）
  - `max_det`（默认 `1000`）

示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

### 2.3 IoT 上报接口

- `POST /telemetry`
- 请求类型：`application/json`
- 请求体字段：
  - `device_id`（必填）
  - `temperature`（可选）
  - `humidity`（可选）
  - `light`（可选）
  - `ts`（可选，ISO 时间）
- 可选请求头：
  - `X-API-Key`（仅当配置了 `IOT_API_KEY` 时需要）

示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d "{\"device_id\":\"pi-001\",\"temperature\":24.6,\"humidity\":58.2,\"light\":301}"
```

### 2.4 IoT 查询接口

- `GET /telemetry/latest?device_id=<id>&limit=<n>`
- `limit` 默认 `100`，最大 `500`
- 可选请求头：`X-API-Key`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry/latest?device_id=pi-001&limit=10"
```

### 2.5 识别历史查询接口

- `GET /history?limit=<n>`
- 从 Blob 容器 `aphid-history` 读取历史 JSON
- `limit` 默认 `50`，最大 `500`

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/history?limit=50"
```

### 2.6 容器内置网页路由

- 预测页：`GET /predict/dashboard`
- 监测页：`GET /telemetry/dashboard`
- 历史页：`GET /history/dashboard`

## 3. 本地网页

网页目录：

- `web_pages/local_web_client.html`（预测）
- `web_pages/telemetry_dashboard.html`（监测）
- `web_pages/history_records.html`（历史）

启动本地静态服务（仓库根目录）：

```bash
python -m http.server 18090
```

打开：

- `http://127.0.0.1:18090/web_pages/local_web_client.html`
- `http://127.0.0.1:18090/web_pages/telemetry_dashboard.html`
- `http://127.0.0.1:18090/web_pages/history_records.html`

三个页面顶部都可互相跳转（预测 / 监测 / 历史）。

## 4. 当前 Azure 资源

资源组：`rg-aphid-yolo-se`  
区域：`swedencentral`

主要资源：

1. Container App：`aca-aphid-yolo`
2. Container Apps Environment：`aca-env-aphid-yolo`
3. ACR：`acraphidyolo2498`
4. Storage Account：`staphid25021201`
5. Log Analytics：`workspace-rgaphidyoloseNxBa`

## 5. 存储逻辑

1. `/predict` 原图写入 Blob：`aphid-images`
2. `/predict` 每次会写一条历史 JSON 到 Blob：`aphid-history`
3. `/telemetry` 写入 Table：`iottelemetry`
4. 当前部署使用同一套 Storage 连接供上述存储功能共用

## 6. 自动部署（GitHub Actions）

工作流：

- `.github/workflows/deploy_containerapp.yml`

触发：

1. push 到 `main`
2. 手动 `workflow_dispatch`

流程：

1. 拉代码
2. 同步 `web_pages/*.html` 到 `.container_yolo26/`
3. Docker 构建
4. 推送 ACR
5. 更新 Container App
6. 调用 `/health` 验证

## 7. 更新模型

1. 替换模型：`.container_yolo26/model/best.pt`
2. 提交推送：
   - `git add .`
   - `git commit -m "Update model"`
   - `git push origin main`
3. 等待 Actions 成功
4. 验证 `/health` 与 `/predict`

## 8. 关键文件

1. `.container_yolo26/server.py`
2. `.container_yolo26/Dockerfile`
3. `.container_yolo26/requirements.txt`
4. `.container_yolo26/model/best.pt`
5. `web_pages/local_web_client.html`
6. `web_pages/telemetry_dashboard.html`
7. `web_pages/history_records.html`
8. `package_yolo26_container.py`
9. `deploy_to_azure.ps1`
10. `.github/workflows/deploy_containerapp.yml`

## 9. 故障排查

1. `/predict` 失败
   - 查看 Container App 日志
   - 确认模型路径 `/app/model/best.pt`
2. `blob_saved=false`
   - 检查 `BLOB_CONNECTION_STRING`
   - 检查 `aphid-images` 权限
3. `/history` 返回 503
   - 检查 `BLOB_CONNECTION_STRING`
   - 检查容器 `aphid-history`
4. `/telemetry` 返回 401
   - 若配置了 `IOT_API_KEY`，需带 `X-API-Key`
5. `/telemetry` 返回 503
   - 检查 `AZURE_STORAGE_CONNECTION_STRING` 与 `TELEMETRY_TABLE`
