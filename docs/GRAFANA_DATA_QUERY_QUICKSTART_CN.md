# Grafana 数据查询简版说明

给同学的最短版本如下。

## 1. 现在怎么查

不要再查 Log Analytics 自定义表。

现在直接查 API：

- `/grafana/telemetry`
- `/grafana/aphidcounts`

基础地址：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 2. 最常用的调用

### 看最近的传感器数据

```text
/grafana/telemetry?device_id=pi-001&limit=50
```

### 看最近的虫子数量

```text
/grafana/aphidcounts?device_id=pi-001&limit=50
```

### 查时间范围

```text
/grafana/telemetry?device_id=pi-001&from=2026-04-20T00:00:00Z&to=2026-04-21T00:00:00Z&limit=500
```

```text
/grafana/aphidcounts?device_id=pi-001&from=2026-04-20T00:00:00Z&to=2026-04-21T00:00:00Z&limit=500
```

## 3. 重点字段

### `/grafana/telemetry`

- `ts`
- `temperature`
- `humidity`
- `pressure_hpa`
- `light`

### `/grafana/aphidcounts`

- `ts`
- `count`
- `device_id`
- `source_device_id`
- `filename`

## 4. 查不到数据先看什么

1. 基础地址对不对
2. `device_id` 对不对
3. 时间范围是不是太短
4. 设备是不是已经把数据写进 Azure Table
5. 你是不是还在查旧的 Log Analytics 表

## 5. 一句话发给同学

> Grafana 现在直接通过 API 查数据，不用 Log Analytics。基础地址用 `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`，传感器数据查 `/grafana/telemetry`，虫子数量查 `/grafana/aphidcounts`。
