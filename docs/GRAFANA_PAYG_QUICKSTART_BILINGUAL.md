# Grafana + API Quick Start (PAYG)

This is the current Grafana document for the PAYG deployment.
If you only read one Grafana document, read this one.

这份文档是当前 PAYG 环境下给 Grafana 用的有效版本。
如果你只看一份 Grafana 文档，就看这份。

## 1. Short Answer / 一句话先说清楚

Grafana should now read data through our API, not through Log Analytics custom tables.

Grafana 现在应该通过我们的 API 读数据，不再走 Log Analytics 自定义表。

Use these API endpoints:
请用这两个接口：

- `/grafana/telemetry`
- `/grafana/aphidcounts`

## 2. Base URL / 基础地址

Current API base URL:
当前 API 基础地址：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 3. What To Query / 该查什么

### Telemetry / 传感器数据

```text
GET /grafana/telemetry?device_id=pi-001&limit=50
```

Optional query parameters:
可选参数：

- `from` : ISO time
- `to` : ISO time
- `limit` : default `500`, max `5000`

Example:

```text
/grafana/telemetry?device_id=pi-001&from=2026-04-20T00:00:00Z&to=2026-04-21T00:00:00Z&limit=500
```

### Aphid Counts / 虫子数量

```text
GET /grafana/aphidcounts?device_id=pi-001&limit=50
```

Optional query parameters:
可选参数：

- `from` : ISO time
- `to` : ISO time
- `limit` : default `500`, max `5000`

Example:

```text
/grafana/aphidcounts?device_id=pi-001&from=2026-04-20T00:00:00Z&to=2026-04-21T00:00:00Z&limit=500
```

## 4. Response Shape / 返回格式

### `/grafana/telemetry`

```json
{
  "device_id": "pi-001",
  "from": "2026-04-20T00:00:00+00:00",
  "to": "2026-04-21T00:00:00+00:00",
  "count": 2,
  "items": [
    {
      "device_id": "pi-001",
      "ts": "2026-04-20T12:00:00+00:00",
      "temperature": 22.4,
      "humidity": 61.2,
      "pressure_hpa": 1012.8,
      "light": 320.0
    }
  ]
}
```

### `/grafana/aphidcounts`

```json
{
  "device_id": "pi-001",
  "from": "2026-04-20T00:00:00+00:00",
  "to": "2026-04-21T00:00:00+00:00",
  "count": 2,
  "items": [
    {
      "device_id": "pi-001",
      "source_device_id": "pi-001",
      "request_id": "example-id",
      "ts": "2026-04-20T12:30:00+00:00",
      "filename": "test.jpg",
      "count": 5,
      "image_blob_name": "image.jpg",
      "history_blob_name": "history.json"
    }
  ]
}
```

## 5. Common Fields / 常用字段

Telemetry fields:
传感器字段：

- `ts`
- `temperature`
- `humidity`
- `pressure_hpa`
- `light`

Aphid count fields:
虫量字段：

- `ts`
- `count`
- `device_id`
- `source_device_id`
- `filename`

## 6. Grafana Side / Grafana 侧怎么接

Use any HTTP/JSON data source plugin your team already has in Grafana.
Then point it to our API base URL and query:

- `/grafana/telemetry`
- `/grafana/aphidcounts`

在 Grafana 里，用你们已有的 HTTP / JSON 数据源插件即可。
把基础地址指向我们的 API，然后分别请求：

- `/grafana/telemetry`
- `/grafana/aphidcounts`

## 7. Troubleshooting / 排查顺序

If Grafana shows no data, check:
如果 Grafana 没数据，先看：

1. Base URL is correct
2. `device_id` is correct
3. `from` / `to` range is not too narrow
4. The device has actually written rows into Azure Table
5. Grafana is calling `/grafana/telemetry` or `/grafana/aphidcounts`, not old Log Analytics tables

## 8. One Message For Teammates / 发给同学的一段话

> Grafana now reads business data through our API, not Log Analytics. Use the API base URL `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`, then query `/grafana/telemetry` and `/grafana/aphidcounts` with `device_id`, and optional `from`, `to`, and `limit`.
