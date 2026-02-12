# 蚜虫检测云端部署与交接文档（中文版）

本文档用于项目交接与团队协作，面向“第一次接触该项目”的同学。  
目标是让任何成员都能基于本文完成：训练、打包、部署、升级模型、验证接口、回滚与排障。

---

## 1. 项目简介

本项目使用 YOLO 模型进行蚜虫检测，并将推理服务部署到 Azure Container Apps。

项目包含以下能力：
- 本地训练模型：`train_yolo26.py`
- 将训练得到的 `best.pt` 打包成推理容器：`package_yolo26_container.py`
- 自动创建/更新 Azure 资源并部署：`deploy_to_azure.ps1`
- 浏览器本地网页调用云端推理：`local_web_client.html`
- 浏览器查看管理员历史记录：`admin_history_client.html`
- 树莓派摄像头采集并调用云端推理：`raspberry_pi_client.py`

在线 API 端点：
- `GET /health`
- `POST /predict`（multipart 图片上传）
- `GET /admin/history`（仅管理员，可通过 `X-Admin-Token` 访问）

---

## 2. 当前线上部署信息（截至 2026-02-12）

订阅：
- `Azure for Students`（`12190bf7-b4d8-4dfa-9a63-01580c6ad868`）

资源组：
- `rg-aphid-yolo-se`

区域：
- `swedencentral`

Azure 资源：
- Container App：`aca-aphid-yolo`
- Container App Environment：`aca-env-aphid-yolo`
- Azure Container Registry：`acraphidyolo2498`

当前活跃版本（Revision）：
- `aca-aphid-yolo--0000002`（`Running` / `Healthy`）

公网地址：
- Health：`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health`
- Predict：`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict`

当前镜像标签：
- `aphid-yolo26:cors1`

说明：
- 已启用 CORS，支持本地浏览器直接调用云端接口。

---

## 3. 代码文件说明

核心文件：
- `train_yolo26.py`：训练入口脚本
- `continue_train_yolo26.py`：继续训练脚本
- `package_yolo26_container.py`：生成容器上下文 `.container_yolo26`
- `deploy_to_azure.ps1`：Azure 自动部署脚本（创建/更新）
- `local_web_client.html`：本地网页客户端（浏览器调用）
- `admin_history_client.html`：管理员历史记录网页
- `raspberry_pi_client.py`：树莓派摄像头推理客户端
- `.container_yolo26/`：容器构建目录（每次打包会重建）

---

## 4. 本地环境要求

必须安装：
- Python 3.9+（当前环境使用过 Python 3.12）
- Docker Desktop（Linux containers 模式）
- Azure CLI
- 可登录的 Azure 账号

推荐：
- PowerShell

安装 Azure CLI（如未安装）：
```powershell
winget install --id Microsoft.AzureCLI -e --source winget
```

若当前终端 `az` 不可用，可用绝对路径调用：
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" --version
```

登录 Azure：
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

---

## 5. 订阅区域限制说明（非常重要）

该订阅存在 Azure Policy 限制，仅允许以下区域部署：
- `swedencentral`
- `italynorth`
- `spaincentral`
- `switzerlandnorth`
- `norwayeast`

如果你用 `eastus`、`uksouth` 等不在列表中的区域，会报策略拒绝（`RequestDisallowedByAzure`）。

---

## 6. 整体流程（训练 -> 打包 -> 部署 -> 验证）

1. 本地训练模型，得到新的 `best.pt`
2. 执行打包脚本，生成 `.container_yolo26`
3. 执行部署脚本，推送镜像并更新 Container App
4. 调用 `/health`、`/predict` 验证
5. 将 URL 提供给网页端/树莓派端使用

---

## 7. 首次部署（或完整重建）

### 7.1 生成容器上下文
```powershell
python package_yolo26_container.py --no-build
```

若指定模型权重路径：
```powershell
python package_yolo26_container.py --model "runs/detect/runs/train/yolo26_aphid_count3/weights/best.pt" --no-build
```

### 7.2 部署到 Azure
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:cors1 `
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" `
  -BlobImageContainer aphid-images `
  -BlobHistoryContainer aphid-history `
  -AdminToken "<SET_ADMIN_TOKEN>" `
  -UseLocalDockerBuild
```

为什么使用 `-UseLocalDockerBuild`：  
该订阅下 `az acr build` 可能被限制（`TasksOperationsNotAllowed`），本地 Docker build/push 更稳定。

---

## 8. 如何升级部署“更好的新模型”（日常最常用）

当你训练出更好的模型（新的 `best.pt`）时，按这个步骤做：

### A. 训练（或继续训练）
示例：
```powershell
python train_yolo26.py --data data.yaml --model yolo26n.pt --epochs 100 --imgsz 640
```

查看最近的 `best.pt`：
```powershell
Get-ChildItem -Path runs -Recurse -File -Filter best.pt | Sort-Object LastWriteTime -Descending | Select-Object -First 5 FullName,LastWriteTime
```

### B. 用新模型打包
```powershell
python package_yolo26_container.py --model "<新的best.pt路径>" --no-build
```

### C. 部署新镜像（建议每次新标签）
不要一直复用 `latest`，建议使用可追踪标签（如日期/版本号）：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:v2026.02.12-2 `
  -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" `
  -BlobImageContainer aphid-images `
  -BlobHistoryContainer aphid-history `
  -AdminToken "<SET_ADMIN_TOKEN>" `
  -UseLocalDockerBuild
```

### D. 部署后验证
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```

图片推理验证：
```powershell
python -c "import requests; f=open('data/val/images/Img_131.jpg','rb'); r=requests.post('https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict', files={'image':('Img_131.jpg', f, 'image/jpeg')}, timeout=120); print(r.status_code); print(r.text[:300])"
```

---

## 9. 回滚策略（新版本有问题时）

如果新版本表现不稳定，直接回滚到已知稳定标签：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 `
  -ResourceGroup rg-aphid-yolo-se `
  -Location swedencentral `
  -RegistryName acraphidyolo2498 `
  -ContainerEnvName aca-env-aphid-yolo `
  -ContainerAppName aca-aphid-yolo `
  -ImageName aphid-yolo26:cors1 `
  -SkipAcrBuild
```

说明：
- `-SkipAcrBuild` 前提是目标镜像已经在 ACR 里存在。

---

## 10. API 接口文档（给前端/设备端/后端联调）

Base URL：
- `https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

### 10.1 `GET /health`
返回示例：
```json
{
  "status": "ok",
  "model_path": "/app/model/best.pt"
}
```

存储行为：
- 每次 `/predict` 会把原图上传到 Blob 容器 `BLOB_CONTAINER_IMAGES`
- 每次 `/predict` 会把结构化结果写入 Blob 容器 `BLOB_CONTAINER_HISTORY`
- 返回中会包含 `request_id` 与 `blob_saved`

### 10.3 `GET /admin/history`
请求头（必填）：
- `X-Admin-Token: <ADMIN_TOKEN>`

Query 参数：
- `limit`（1-200，默认 50）

示例：
```bash
curl -H "X-Admin-Token: <ADMIN_TOKEN>" \
  "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/admin/history?limit=20"
```

返回：
- `records` 数组，按最新到最旧排序。

### 10.2 `POST /predict`
请求：
- `Content-Type: multipart/form-data`
- 文件字段：`image`（必填）
- Query 参数（可选）：
  - `conf`（float，默认 `0.25`）
  - `iou`（float，默认 `0.45`）
  - `imgsz`（int，默认 `640`）
  - `max_det`（int，默认 `1000`）

`curl` 示例：
```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/predict?conf=0.25&iou=0.45&imgsz=640&max_det=1000" \
  -F "image=@test.jpg"
```

返回示例：
```json
{
  "filename": "test.jpg",
  "count": 6,
  "detections": [
    {
      "class_id": 0,
      "class_name": "aphid",
      "confidence": 0.79,
      "bbox_xyxy": [645.5, 163.3, 723.2, 271.0]
    }
  ]
}
```

---

## 11. 本地网页客户端使用（浏览器）

文件：
- `local_web_client.html`

启动本地静态服务（端口可改）：
```powershell
python -m http.server 18090 --bind 127.0.0.1
```

访问：
- `http://127.0.0.1:18090/local_web_client.html`

如果端口被占用：
```powershell
netstat -ano | findstr :18090
```

换一个空闲端口（如 `18888`）即可。

管理员历史页：
- `http://127.0.0.1:18090/admin_history_client.html`
- 输入 endpoint 和管理员 token 后加载历史记录。

---

## 12. 树莓派客户端使用

树莓派安装依赖：
```bash
pip install requests opencv-python
```

运行：
```bash
python raspberry_pi_client.py \
  --url https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io \
  --camera 0 \
  --interval 10 \
  --conf 0.25
```

行为说明：
- 摄像头拍照
- 上传到云端 `/predict`
- 打印检测数量与完整 JSON

---

## 13. 运维与排障命令

### 13.1 查看 revision 状态
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" containerapp revision list -g rg-aphid-yolo-se -n aca-aphid-yolo -o table
```

### 13.2 查看服务日志
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" containerapp logs show -g rg-aphid-yolo-se -n aca-aphid-yolo --tail 200
```

---

## 14. 常见问题与对应处理

1) `az` 找不到  
使用绝对路径执行：
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

2) 区域策略错误（`RequestDisallowedByAzure`）  
只用第 5 节允许的区域。

3) ACR 云端构建失败（`TasksOperationsNotAllowed`）  
使用 `-UseLocalDockerBuild`。

4) 浏览器 `Failed to fetch`（跨域）  
确认部署版本包含 CORS（当前 `cors1` 已包含）。

5) 历史记录未写入（`blob_saved=false`）  
部署时请传入：
- `BLOB_CONNECTION_STRING`
- `BLOB_CONTAINER_IMAGES`
- `BLOB_CONTAINER_HISTORY`
- `ADMIN_TOKEN`

6) 容器报 `libxcb.so.1` 缺失  
确认 Dockerfile 安装了 OpenCV 相关系统库（当前脚本已处理）。

7) Docker daemon 未启动  
先启动 Docker Desktop，再执行部署。

---

## 15. 安全建议

- 不要把账号密钥、密码写入仓库。
- 部署时终端会用到 ACR admin 凭据，日志与历史命令视为敏感信息。
- 后续若走生产，建议改为 Managed Identity + 最小权限访问。

---

## 16. 团队协作建议（建议执行）

建议每次发布记录以下内容（可放在项目周报或 Release Note）：
- 模型来源（训练 run 路径、指标）
- 镜像标签（如 `aphid-yolo26:v2026.02.13-1`）
- 部署时间
- 关键验证图像与结果
- 若回滚，记录回滚原因

---

## 17. 命令速查（复制即用）

登录：
```powershell
& "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" login
```

打包最新模型：
```powershell
python package_yolo26_container.py --no-build
```

部署新版本：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_to_azure.ps1 -ResourceGroup rg-aphid-yolo-se -Location swedencentral -RegistryName acraphidyolo2498 -ContainerEnvName aca-env-aphid-yolo -ContainerAppName aca-aphid-yolo -ImageName aphid-yolo26:vNEXT -BlobConnectionString "<AZURE_STORAGE_CONNECTION_STRING>" -BlobImageContainer aphid-images -BlobHistoryContainer aphid-history -AdminToken "<SET_ADMIN_TOKEN>" -UseLocalDockerBuild
```

健康检查：
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/health"
```
