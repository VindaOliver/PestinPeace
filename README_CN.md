# PestinPeace 推理服务说明

这个仓库提供基于 YOLO 的蚜虫识别 API，部署在 Azure Container Apps。

## 当前接口

基础地址：

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

可用接口：

- `GET /health`
- `POST /predict`

当前版本已移除管理员鉴权和历史记录接口（没有 `/admin/history`）。

## 预测调用方式

`POST /predict` 使用 `multipart/form-data`：

- 表单字段：`image`（必填）
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

## Blob 存储行为

如果配置了 Blob，`/predict` 每次会把原图写入：

- 容器：`aphid-images`

当前 API 不再写历史 JSON。

## 本地网页调用

在仓库根目录启动静态服务：

```bash
python -m http.server 18090
```

浏览器打开：

`http://127.0.0.1:18090/local_web_client.html`

## 新模型部署（GitHub Actions + ACR）

1. 替换模型文件：
   - `.container_yolo26/model/best.pt`
2. （可选）重新生成容器上下文：
   - `python package_yolo26_container.py --no-build`
3. 提交并推送到 `main`：
   - `git add .container_yolo26`
   - `git commit -m "Update model"`
   - `git push origin main`

推送后会自动执行：

- Docker Build
- 推送到 ACR
- 更新 Azure Container App 镜像

## 关键文件

- `.container_yolo26/server.py`：线上 API 代码
- `.container_yolo26/model/best.pt`：部署模型
- `.github/workflows/deploy_containerapp.yml`：CI/CD 工作流
- `package_yolo26_container.py`：生成 `.container_yolo26` 的脚本
