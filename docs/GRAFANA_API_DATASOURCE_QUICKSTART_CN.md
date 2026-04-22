# Grafana 通过 API 取数快速说明

这份文档是给负责 Grafana 的同学用的。
目标很简单：让 Grafana 直接通过我们项目的 API 读取温湿度和虫量数据，不再走 Log Analytics。

## 1. 一句话先说清楚

Grafana 现在应该读取这两个 API：

- `/grafana/telemetry`
- `/grafana/aphidcounts`

当前线上 API 基础地址：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

## 2. 在 Grafana 里怎么配

1. 进入 Grafana UI。
2. 打开 `Connections` 或 `Data sources`。
3. 新增一个支持 HTTP / JSON 的数据源插件。
4. 常见可用插件：
   - `JSON API`
   - `Infinity`
   - 其他团队已经装好的 HTTP / JSON 插件
5. 把基础地址填成：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

6. 保存并测试。

## 3. 该请求什么地址

### 温湿度和气压

```text
/grafana/telemetry?device_id=pi-001&limit=50
```

如果要查时间范围，可以加：

```text
/grafana/telemetry?device_id=pi-001&from=2026-04-21T00:00:00Z&to=2026-04-21T23:59:59Z&limit=500
```

### 虫量

```text
/grafana/aphidcounts?device_id=pi-001&limit=50
```

如果要查时间范围，可以加：

```text
/grafana/aphidcounts?device_id=pi-001&from=2026-04-21T00:00:00Z&to=2026-04-21T23:59:59Z&limit=500
```

## 4. 返回数据长什么样

两个接口都会返回：

- `device_id`
- `from`
- `to`
- `count`
- `items`

真正画图时，主要看 `items` 里的字段。

### `/grafana/telemetry` 重点字段

- `ts`
- `temperature`
- `humidity`
- `pressure_hpa`
- `light`

### `/grafana/aphidcounts` 重点字段

- `ts`
- `count`
- `device_id`
- `source_device_id`
- `filename`

## 5. Grafana 里常见怎么画

### 温度折线图

- 时间字段：`ts`
- 数值字段：`temperature`

### 湿度折线图

- 时间字段：`ts`
- 数值字段：`humidity`

### 气压折线图

- 时间字段：`ts`
- 数值字段：`pressure_hpa`

### 虫量变化图

- 时间字段：`ts`
- 数值字段：`count`

## 6. 如果 Grafana 里没数据，先查这几件事

1. 基础地址是不是对的。
2. 请求路径是不是 `/grafana/telemetry` 或 `/grafana/aphidcounts`。
3. `device_id` 是不是对的。
4. 时间范围是不是太窄。
5. 设备最近是不是真的写入了新数据。

## 7. 最短交接话术

可以直接把这段发给同学：

> Grafana 现在不要再查 Log Analytics 业务表了，直接查我们的 API。基础地址是 `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`。温湿度用 `/grafana/telemetry`，虫量用 `/grafana/aphidcounts`，都要带 `device_id`，也可以加 `from`、`to`、`limit`。
