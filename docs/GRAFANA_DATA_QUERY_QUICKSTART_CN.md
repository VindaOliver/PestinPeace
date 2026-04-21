# Grafana 数据查询简版说明

这份文档是写给同学的最短版本。
目标只有一个：进 Grafana 后，知道该查什么、怎么查。

## 1. 先记住这件事

Grafana 现在不要直接查原始 Azure Table：

- `iottelemetry`
- `aphidcounts`

Grafana 应该查已经同步进 Log Analytics 的两张表：

- `IoTTelemetry_CL`
- `AphidCounts_CL`

## 2. 在 Grafana 里怎么选

1. 打开你们的 Grafana
2. 进入 `Azure Monitor` 数据源
3. Query type 选 `Logs`
4. Workspace 选 `workspace-rgaphidyolopaygK1ST`

## 3. 最常用的查询

### 3.1 看最近的传感器数据

```kusto
IoTTelemetry_CL
| order by TimeGenerated desc
| take 20
```

### 3.2 看最近的虫子识别数量

```kusto
AphidCounts_CL
| order by TimeGenerated desc
| take 20
```

### 3.3 按设备查看传感器数据

```kusto
IoTTelemetry_CL
| where DeviceId == "pi-001"
| order by TimeGenerated desc
| take 50
```

### 3.4 按设备查看虫子数量

```kusto
AphidCounts_CL
| where DeviceId == "pi-001"
| order by TimeGenerated desc
| take 50
```

## 4. 如果要画图

### 4.1 温度小时趋势

```kusto
IoTTelemetry_CL
| summarize avg_temp = avg(Temperature) by bin(TimeGenerated, 1h), DeviceId
| order by TimeGenerated asc
```

### 4.2 每天虫子总数趋势

```kusto
AphidCounts_CL
| summarize aphid_total = sum(Count) by bin(TimeGenerated, 1d), DeviceId
| order by TimeGenerated asc
```

## 5. 常见字段是什么意思

### `IoTTelemetry_CL`

- `DeviceId`: 设备编号
- `Temperature`: 温度
- `Humidity`: 湿度
- `PressureHpa`: 气压
- `Light`: 光照
- `TimeGenerated`: 进入 Log Analytics 的时间
- `Ts`: 原始记录时间

### `AphidCounts_CL`

- `DeviceId`: 当前记录对应的设备编号
- `SourceDeviceId`: 原始请求里的设备编号
- `Count`: 识别出来的虫子数量
- `Filename`: 图片文件名
- `RequestId`: 这次识别请求的 ID
- `TimeGenerated`: 进入 Log Analytics 的时间
- `Ts`: 原始记录时间

## 6. 查不到数据时先看什么

按这个顺序排查：

1. 数据源是不是 `Azure Monitor`
2. Query type 是不是 `Logs`
3. Workspace 是不是 `workspace-rgaphidyolopaygK1ST`
4. 时间范围是不是太短
5. 设备号是不是写错了
6. 你是不是误查成了 `iottelemetry` / `aphidcounts`

## 7. 一句话发给同学

可以直接转发这段：

> Grafana 里不要直接查 `iottelemetry` 和 `aphidcounts`，要查已经同步进 Log Analytics 的 `IoTTelemetry_CL` 和 `AphidCounts_CL`。数据源选 `Azure Monitor`，Query type 选 `Logs`，Workspace 选 `workspace-rgaphidyolopaygK1ST`。
