# PestinPeace 项目说明（中文）

PestinPeace 是一个基于 YOLO 的蚜虫检测与计数项目，当前部署在 Azure Container Apps。

当前仓库地址：`https://github.com/VindaOliver/PestinPeace`

## 1. 当前能力

当前仓库已支持：

- Azure 云端推理 API
- 推理图片与历史结果写入 Azure Blob
- 管理员历史记录（Entra 登录，推荐）
- 本地网页调用推理与历史接口
- GitHub Actions 自动部署（Build -> Push ACR -> 更新 Container App）

## 2. 系统结构

- 推理容器：FastAPI + Ultralytics YOLO
- Azure Blob：
  - 图片容器
  - 历史 JSON 容器
- Azure Container App 对外接口
- 本地页面：
  - `local_web_client.html`（预测）
  - `admin_history_entra.html`（管理员历史）

## 3. API 接口

当前部署地址：

`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

### `GET /health`

返回服务状态与鉴权模式。

### `POST /predict`

- 请求类型：`multipart/form-data`
- 文件字段：`image`（必填）
- 可选参数：`conf`、`iou`、`imgsz`、`max_det`

返回字段包含：

- `request_id`
- `count`
- `detections`
- `blob_saved`

### `GET /admin/history`

管理员接口。

鉴权规则：

- 若启用 Entra：使用 `Authorization: Bearer <token>`
- 若未启用 Entra：使用 `X-Admin-Token`

## 4. 鉴权（当前为 Entra）

当前部署已启用 Entra 管理员鉴权。

后端环境变量：

- `ENTRA_TENANT_ID`
- `ENTRA_CLIENT_ID`
- `ENTRA_AUDIENCE`（可选）
- `ENTRA_ALLOWED_GROUP_IDS`（可选）
- `ENTRA_ALLOWED_USER_OBJECT_IDS`（可选）
- `ENTRA_ALLOWED_ROLES`（可选）

## 5. 本地网页使用

### 5.1 预测页

- 文件：`local_web_client.html`
- 启动本地静态服务：

```powershell
python -m http.server 18090 --bind 127.0.0.1
```

- 打开：

`http://127.0.0.1:18090/local_web_client.html`

### 5.2 Entra 管理页

- 文件：`admin_history_entra.html`
- 打开：

`http://127.0.0.1:18090/admin_history_entra.html`

填写：

- API base URL
- Tenant ID
- Client ID（SPA 应用）
- Scope（可留空，使用 idToken 模式）

然后点击：

- `Sign In`
- `Load History`

## 6. Azure 部署命令

### 6.1 生成容器上下文

```powershell
python package_yolo26_container.py --no-build
```

### 6.2 部署

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 \
  -ResourceGroup rg-aphid-yolo-se \
  -Location swedencentral \
  -RegistryName acraphidyolo2498 \
  -ContainerEnvName aca-env-aphid-yolo \
  -ContainerAppName aca-aphid-yolo \
  -ImageName aphid-yolo26:vNEXT \
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" \
  -BlobImageContainer aphid-images \
  -BlobHistoryContainer aphid-history \
  -EntraTenantId "<TENANT_ID>" \
  -EntraClientId "<CLIENT_ID>" \
  -EntraAllowedUserObjectIds "<USER_OBJECT_ID>" \
  -UseLocalDockerBuild
```

## 7. GitHub Actions 自动部署

工作流文件：

- `.github/workflows/deploy_containerapp.yml`

触发后自动执行：

1. 从 `.container_yolo26` 构建镜像
2. 推送到 ACR
3. 更新 Container App 镜像
4. 调用 `/health` 验证

配置文档见：

- `GITHUB_ACTIONS_SETUP.md`

## 8. 更新更好的模型

建议流程：

1. 替换模型并重生成容器上下文：

```powershell
python package_yolo26_container.py --no-build
```

2. 提交并 push 到 `main`
3. Actions 自动部署
4. 用 `/health` 与样例 `/predict` 验证

## 9. 仓库范围说明

本仓库聚焦“部署与协作”。

默认不纳入 git：

- 训练数据（`data/`）
- 训练产物（`runs/`）
- 本地训练脚本与本地预训练权重（已忽略）

## 10. 常见问题

### `msal is not defined`

`admin_history_entra.html` 已支持多 CDN + 本地 `./vendor/msal-browser.min.js` 回退。

### `AADSTS9002326`

Entra 应用需要配置 `spa.redirectUris`，不能只配 `web.redirectUris`。

### `blob_saved=false`

检查：

- `BLOB_CONNECTION_STRING`
- `BLOB_CONTAINER_IMAGES`
- `BLOB_CONTAINER_HISTORY`

### 端口冲突

改用其它端口：

```powershell
python -m http.server 18888 --bind 127.0.0.1
```

## 11. 安全建议

- 不要提交任何密钥。
- 生产环境建议使用 Entra + OIDC。
- 若历史中有暴露 token/key，立即轮换。
