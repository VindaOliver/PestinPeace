# Grafana + API Quick Start (PAYG)

This is the current Grafana guide for the PAYG deployment.
If your teammate only reads one Grafana document, read this one.

这份文档是当前 PAYG 环境下给 Grafana 用的主文档。
如果队友只看一份 Grafana 文档，就看这份。

## 1. Short Answer / 一句话先说清楚

Grafana should now read business data through our API, not through Log Analytics custom tables.

Grafana 现在应该通过我们的 API 读取业务数据，而不是通过 Log Analytics 业务表。

Use these API endpoints:

- `/grafana/telemetry`
- `/grafana/aphidcounts`

## 2. Base URL / 基础地址

Current API base URL:

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 3. What To Query / 该查什么

### Telemetry / 传感器数据

```text
GET /grafana/telemetry?device_id=pi-001&limit=50
```

Optional query parameters:

- `from`: ISO time
- `to`: ISO time
- `limit`: default `500`, max `5000`

Example:

```text
/grafana/telemetry?device_id=pi-001&from=2026-04-20T00:00:00Z&to=2026-04-21T00:00:00Z&limit=500
```

### Detection Counts / 虫量数据

```text
GET /grafana/aphidcounts?device_id=pi-001&limit=50
```

Optional query parameters:

- `from`: ISO time
- `to`: ISO time
- `limit`: default `500`, max `5000`

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
      "count_mean": 5,
      "aphid_count": 5,
      "slug_count": 1,
      "total_count": 6,
      "class_breakdown": {
        "aphid": 5,
        "slug": 1
      },
      "image_blob_name": "image.jpg",
      "history_blob_name": "history.json"
    }
  ]
}
```

## 5. Common Fields / 常用字段

Telemetry fields:

- `ts`
- `temperature`
- `humidity`
- `pressure_hpa`
- `light`

Detection count fields:

- `ts`
- `aphid_count`
- `slug_count`
- `total_count`
- `count`
- `count_mean`
- `class_breakdown`
- `device_id`
- `source_device_id`
- `filename`

Recommended Grafana usage:

- use `aphid_count` for aphid trend and anything aligned with forecast / decision
- use `slug_count` for slug monitoring
- use `total_count` for overall detection volume
- treat legacy `count` as compatibility-only and equivalent to `aphid_count`

推荐的 Grafana 用法：

- `aphid_count` 用于 aphid 趋势图，以及和 forecast / decision 对齐的图
- `slug_count` 用于 slug 独立监测图
- `total_count` 用于总检测量展示
- 旧字段 `count` 现在只作为兼容字段，语义等于 `aphid_count`

## 6. Grafana Side / Grafana 里怎么接

Use any HTTP/JSON data source plugin your team already has in Grafana.
Then point it to our API base URL and query:

- `/grafana/telemetry`
- `/grafana/aphidcounts`

If a teammate needs exact Grafana setup steps, read:

`docs/GRAFANA_API_DATASOURCE_QUICKSTART_CN.md`

## 7. Troubleshooting / 排查顺序

If Grafana shows no data, check:

1. Base URL is correct
2. `device_id` is correct
3. `from` / `to` range is not too narrow
4. The device has actually written rows into Azure Table
5. Grafana is calling `/grafana/telemetry` or `/grafana/aphidcounts`, not any old Log Analytics path
6. Grafana panel is using `aphid_count` / `slug_count` / `total_count`, not only the old `count`

## 8. One Message For Teammates / 发给同学的一段话

> Grafana now reads business data through our API, not Log Analytics. Use the API base URL `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`, then query `/grafana/telemetry` and `/grafana/aphidcounts` with `device_id`, and optional `from`, `to`, and `limit`. For pest charts, prefer `aphid_count`, `slug_count`, and `total_count` instead of only the legacy `count`.
