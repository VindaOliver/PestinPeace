# 树莓派传感器数据接口上传说明

本文只说明：你已经拿到温湿度等数据后，如何按项目接口格式上传到后端。

## 1. 上传目标接口

- 上传：`POST /telemetry`
- 查询验证：`GET /telemetry/latest`
- Base URL 示例：`https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io`

完整上传地址示例：

```text
https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry
```

## 2. 上传 JSON 格式

`POST /telemetry` 请求体 `Content-Type: application/json`，字段如下：

- `device_id`：`string`，必填，设备唯一标识（示例：`pi-001`）
- `temperature`：`number`，可选，温度（摄氏度）
- `humidity`：`number`，可选，相对湿度（百分比）
- `light`：`number`，可选，光照值（按你们设备单位）
- `ts`：`string`，可选，ISO8601 时间（建议 UTC）

示例请求体：

```json
{
  "device_id": "pi-001",
  "temperature": 24.6,
  "humidity": 58.2,
  "light": 301,
  "ts": "2026-03-09T13:22:11Z"
}
```

说明：

- `ts` 不传也可以，后端会用接收时的 UTC 时间。
- 推荐固定 `device_id`，便于后续按设备查询。

## 3. 上传成功返回格式

HTTP 200 示例：

```json
{
  "status": "ok",
  "device_id": "pi-001",
  "ts": "2026-03-09T13:22:11+00:00"
}
```

## 4. 上传示例（直接可用）

### 4.1 curl

```bash
curl -X POST "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d "{\"device_id\":\"pi-001\",\"temperature\":24.6,\"humidity\":58.2,\"light\":301}"
```

### 4.2 Python（requests）

```python
from datetime import datetime, timezone
import requests

base = "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io"

payload = {
    "device_id": "pi-001",
    "temperature": 24.6,
    "humidity": 58.2,
    "light": 301,
    "ts": datetime.now(timezone.utc).isoformat(),
}

headers = {"Content-Type": "application/json"}

resp = requests.post(f"{base}/telemetry", json=payload, headers=headers, timeout=20)
print(resp.status_code, resp.text)
resp.raise_for_status()
```

## 5. 查询上传结果（验证）

请求：

```bash
curl "https://aca-aphid-yolo.jollystone-e01fd827.swedencentral.azurecontainerapps.io/telemetry/latest?device_id=pi-001&limit=10"
```

返回结构示例：

```json
{
  "device_id": "pi-001",
  "count": 2,
  "items": [
    {
      "device_id": "pi-001",
      "ts": "2026-03-09T13:22:11+00:00",
      "temperature": 24.6,
      "humidity": 58.2,
      "light": 301
    }
  ]
}
```

## 6. 组员对接时的最小要求

1. 采集侧能提供 `device_id + temperature + humidity`（`light/ts` 可选）
2. 按上面的 JSON 结构调用 `POST /telemetry`
3. 用 `GET /telemetry/latest` 确认数据已入库

只要这 3 步完成，就完成了“拿到传感器数据 -> 通过接口上传”的对接。
