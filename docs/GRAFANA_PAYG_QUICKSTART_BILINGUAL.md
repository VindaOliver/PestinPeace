# Grafana + Azure Monitor Quick Start (PAYG)

This is the current Grafana document for the PAYG subscription.
如果你只看一份 Grafana 文档，就看这份。

## 1. The Short Answer / 一句话先说清楚

We are already on the new PAYG subscription.
我们现在已经切到新的 PAYG 订阅。

Grafana can query:
Grafana 现在可以查：

- Azure Monitor logs and metrics
- `ContainerAppConsoleLogs_CL`
- `ContainerAppSystemLogs_CL`
- `AppRequests`
- `AppTraces`
- `IoTTelemetry_CL`
- `AphidCounts_CL`

Important:
重点：

- `iottelemetry` and `aphidcounts` are still the original Azure Tables
- Grafana should **not** try to query those source tables directly
- Grafana should query the mirrored Log Analytics custom tables instead:
  - `IoTTelemetry_CL`
  - `AphidCounts_CL`

## 2. Current Azure Environment / 当前 Azure 环境

- Subscription Name: `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Resource Group: `rg-aphid-yolo-payg`
- Region: `swedencentral`
- Container App: `aca-aphid-yolo`
- App URL: `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`
- ACR: `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Log Analytics Workspace: `workspace-rgaphidyolopaygK1ST`

## 3. Grafana Azure Monitor Data Source Values / Grafana 连接 Azure Monitor 要填什么

Use these values:
在 Grafana 的 Azure Monitor data source 页面填：

- Authentication: `Service Principal`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Client Secret: ask the project owner for the current secret
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

Then:
然后：

1. Click `Save & Test`
2. If it succeeds, start creating panels

## 4. What To Query Now / 现在该查什么

### Platform And App Logs / 平台和应用日志

```kusto
ContainerAppConsoleLogs_CL
| order by TimeGenerated desc
| take 20
```

```kusto
ContainerAppSystemLogs_CL
| order by TimeGenerated desc
| take 20
```

```kusto
AppRequests
| project TimeGenerated, Name, ResultCode, DurationMs, Success
| order by TimeGenerated desc
| take 20
```

```kusto
AppTraces
| project TimeGenerated, SeverityLevel, Message
| order by TimeGenerated desc
| take 20
```

### Business Tables Mirrored Into Log Analytics / 已同步进 Log Analytics 的业务表

```kusto
IoTTelemetry_CL
| order by TimeGenerated desc
| take 20
```

```kusto
AphidCounts_CL
| order by TimeGenerated desc
| take 20
```

### Query By Device / 按 device_id 查

```kusto
IoTTelemetry_CL
| where DeviceId == "pi-001"
| order by TimeGenerated desc
| take 50
```

```kusto
AphidCounts_CL
| where DeviceId == "pi-001"
| order by TimeGenerated desc
| take 50
```

### Make A Time Series / 做时间序列图

```kusto
IoTTelemetry_CL
| summarize avg_temp = avg(Temperature) by bin(TimeGenerated, 1h), DeviceId
| order by TimeGenerated asc
```

```kusto
AphidCounts_CL
| summarize aphid_events = count(), aphid_total = sum(Count) by bin(TimeGenerated, 1d), DeviceId
| order by TimeGenerated asc
```

## 5. What Not To Do / 不要怎么查

Do not expect Grafana Azure Monitor to query these source tables directly:
不要指望 Grafana Azure Monitor 直接查这两张源表：

- `iottelemetry`
- `aphidcounts`

Reason:
原因：

- they live in Azure Table Storage
- Azure Monitor data source is for Azure Monitor / Log Analytics data
- for Grafana, use the mirrored custom tables:
  - `IoTTelemetry_CL`
  - `AphidCounts_CL`

## 6. Metrics / 如果要查 Metrics

For CPU / memory / request-style metrics:
如果你想查 CPU、内存、请求量这类指标：

1. Select data source `Azure Monitor`
2. Set query type to `Metrics`
3. Resource type: `Microsoft.App/containerApps`
4. Resource: `aca-aphid-yolo`
5. Pick the metric you need

## 7. Troubleshooting / 排查顺序

If Grafana returns no data, check in this order:
如果 Grafana 没数据，按这个顺序排查：

1. Did `Save & Test` succeed?
2. Are Tenant ID / Client ID / Client Secret / Subscription ID correct?
3. Did you select the correct workspace `workspace-rgaphidyolopaygK1ST`?
4. Is the query type set to `Logs` when running KQL?
5. Is the time range too short?
6. Are you accidentally querying the source Azure Tables instead of `IoTTelemetry_CL` / `AphidCounts_CL`?

## 8. One Short Message For Teammates / 发给同伴的一段短说明

You can copy this:
你可以直接转发这段：

> We are already on the PAYG subscription. Grafana can query `ContainerAppConsoleLogs_CL`, `ContainerAppSystemLogs_CL`, `AppRequests`, `AppTraces`, and the mirrored business tables `IoTTelemetry_CL` and `AphidCounts_CL` in `workspace-rgaphidyolopaygK1ST`. Do not try to query the original Azure Tables `iottelemetry` and `aphidcounts` directly from Grafana.
