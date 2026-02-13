# PestinPeace 项目说明（团队交接版）

本文档面向第一次接手本项目的同学，目标是让你快速理解：

1. Azure 上有哪些资源、分别做什么
2. 线上预测接口怎么调用
3. 新模型如何发布上线
4. 出问题时如何定位

---

## 1. 项目目标与当前状态

### 1.1 项目目标

本项目提供一个云端虫害识别服务：

1. 客户端上传图片
2. 服务端运行 YOLO 模型推理
3. 返回检测框、类别、置信度、计数
4. 可选把上传原图存入 Azure Blob

### 1.2 当前线上状态（已确认）

1. 线上地址：
   `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`
2. 当前开放接口：
   - `GET /health`
   - `POST /predict`
3. 当前版本已移除管理员历史接口（无 `/admin/history`）

---

## 2. Azure 架构与资源说明

资源组：`rg-aphid-yolo-se`  
区域：`swedencentral`

当前资源组中主要资源：

1. `aca-aphid-yolo`（Container App）
   - 真正对外提供推理 API 的服务实例
   - 域名、revision、副本状态都在这里看

2. `aca-env-aphid-yolo`（Container Apps Environment）
   - Container App 的运行环境底座
   - 管理网络、日志接入、扩缩容环境能力

3. `acraphidyolo2498`（Azure Container Registry, ACR）
   - 存放 Docker 镜像
   - GitHub Actions 把镜像 push 到这里
   - Container App 再从这里拉镜像部署

4. `staphid25021201`（Storage Account）
   - Blob 存储账号
   - 当前用于保存 `/predict` 上传原图
   - 主要容器：`aphid-images`

5. `workspace-rgaphidyoloseNxBa`（Log Analytics Workspace）
   - 采集与查询运行日志、监控数据
   - 用于问题排查与指标分析

一句话理解链路：

`代码/模型 -> 构建镜像 -> 推送 ACR -> Container App 更新 -> 提供 /predict -> 图片写入 Blob`

---

## 3. 线上接口说明

基地址：

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

### 3.1 健康检查接口

- 方法：`GET`
- 路径：`/health`
- 用途：确认服务可用、模型路径、Blob 初始化状态

示例：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

典型返回：

```json
{
  "status": "ok",
  "model_path": "/app/model/best.pt",
  "blob_enabled": true,
  "blob_init_error": null
}
```

### 3.2 预测接口

- 方法：`POST`
- 路径：`/predict`
- Content-Type：`multipart/form-data`
- 必填字段：`image`

可选 query 参数：

1. `conf`（默认 `0.25`）
2. `iou`（默认 `0.45`）
3. `imgsz`（默认 `640`）
4. `max_det`（默认 `1000`）

调用示例：

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

返回说明（核心字段）：

1. `request_id`：请求唯一编号
2. `count`：检测目标数量
3. `detections`：检测框数组（类别、置信度、bbox）
4. `blob_saved`：是否成功写入 Blob
5. `image_blob_name` / `image_blob_url`：若写入成功会返回
6. `storage_error`：写入失败时会返回错误原因

---

## 4. Blob 存储策略

当前策略：

1. 每次 `/predict` 会尝试上传原图到 Blob
2. 默认容器：`aphid-images`
3. 当前版本不再写历史 JSON 记录

在哪里看上传结果：

1. Azure Portal -> `Storage accounts` -> `staphid25021201`
2. `Data storage` -> `Containers`
3. 打开 `aphid-images`

---

## 5. 本地调用方式

### 5.1 本地网页

在仓库根目录运行：

```bash
python -m http.server 18090
```

浏览器打开：

`http://127.0.0.1:18090/local_web_client.html`

### 5.2 Python 调用

可用示例脚本自行调用 `/predict`，核心是：

1. `POST` + `multipart/form-data`
2. `image` 作为文件字段上传

---

## 6. 代码结构（关键文件）

1. `.container_yolo26/server.py`
   - FastAPI 服务
   - YOLO 推理逻辑
   - Blob 上传逻辑

2. `.container_yolo26/model/best.pt`
   - 当前部署模型文件

3. `.container_yolo26/Dockerfile`
   - 推理服务镜像构建定义

4. `.github/workflows/deploy_containerapp.yml`
   - CI/CD 工作流（push main 自动部署）

5. `package_yolo26_container.py`
   - 生成容器上下文（server.py、Dockerfile、requirements、model）

6. `deploy_to_azure.ps1`
   - 手动创建/更新 Azure 资源的部署脚本

---

## 7. Azure 从 0 创建流程（手动路线）

以下是“新同学独立开一套环境”的推荐顺序：

1. 登录 Azure：
   `az login`
2. 创建资源组（RG）
3. 创建 ACR
4. 创建 Container Apps Environment
5. 创建 Storage Account
6. 创建 Blob 容器 `aphid-images`
7. 准备容器上下文 `.container_yolo26`
8. 构建并推送镜像到 ACR
9. 创建或更新 Container App 指向新镜像
10. 配置环境变量：
    - `MODEL_PATH=/app/model/best.pt`
    - `BLOB_CONTAINER_IMAGES=aphid-images`
    - `BLOB_CONNECTION_STRING`（secret）
11. 验证 `/health` 与 `/predict`

说明：你也可以直接用 `deploy_to_azure.ps1` 自动执行大部分步骤。

---

## 8. GitHub Actions 自动部署流程（当前主路线）

触发方式：

1. push 到 `main`
2. 或手动 `workflow_dispatch`

工作流文件：

`.github/workflows/deploy_containerapp.yml`

执行步骤：

1. Checkout 代码
2. 解析部署变量（支持默认值）
3. 校验容器上下文文件
4. 通过 OIDC 登录 Azure
5. Docker Build
6. Push 到 ACR
7. 更新 Container App 镜像
8. 调用 `/health` 验证

关键仓库变量（建议配置）：

1. `ACR_NAME`
2. `RESOURCE_GROUP`
3. `CONTAINER_APP_NAME`
4. `IMAGE_REPO`
5. `AZURE_CLIENT_ID`
6. `AZURE_TENANT_ID`
7. `AZURE_SUBSCRIPTION_ID`

---

## 9. 新模型上线标准流程

1. 替换模型：
   `.container_yolo26/model/best.pt`
2. 可选重新生成上下文：
   `python package_yolo26_container.py --no-build`
3. 提交代码：
   - `git add .container_yolo26`
   - `git commit -m "Update model"`
4. 推送到主分支：
   `git push origin main`
5. 在 GitHub Actions 确认 workflow 绿色通过
6. 验证线上：
   - `GET /health`
   - 用真实图片调用 `POST /predict`

---

## 10. 运维检查与排错

### 10.1 看部署是否成功

1. GitHub -> Actions -> 查看最新 run
2. Azure Portal -> Container App -> `Revisions and replicas`
3. 确认当前镜像 tag 与最新 commit 对应

### 10.2 看服务是否健康

1. 访问 `/health`
2. `status` 必须是 `ok`
3. `blob_enabled` 建议为 `true`

### 10.3 常见问题

1. `blob_saved=false`
   - 检查 `BLOB_CONNECTION_STRING` 是否正确
   - 检查存储账号权限/网络设置

2. `/predict` 5xx
   - 看 Container App `Log stream`
   - 看 Log Analytics 查询异常栈

3. GitHub Actions 失败
   - 检查 OIDC 三元组变量：Client/Tenant/Subscription
   - 检查服务主体是否有 `AcrPush` 和资源组 `Contributor`

---

## 11. 团队协作建议

1. 主分支只合并通过测试和验证的提交
2. 每次上线模型都记录：
   - 模型来源
   - 训练数据版本
   - 评估指标
   - 对应 commit hash
3. 每次部署后固定做两步验收：
   - `/health` 成功
   - 至少 1 张真实图片 `/predict` 成功

---

## 12. 快速入口索引

1. 线上 API：
   `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`
2. 本地网页：
   `http://127.0.0.1:18090/local_web_client.html`
3. CI/CD 配置：
   `.github/workflows/deploy_containerapp.yml`
4. 线上服务代码：
   `.container_yolo26/server.py`

