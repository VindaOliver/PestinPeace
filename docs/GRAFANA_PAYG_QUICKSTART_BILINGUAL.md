# Grafana + Azure Monitor Quick Start (Current PAYG) / Grafana + Azure Monitor 当前 PAYG 快速说明

This is the **current** document for the new PAYG subscription.  
这份文档是**当前有效**的版本，基于新的 PAYG 订阅。

If you only read one Grafana document, read this one.  
如果你只看一份 Grafana 文档，就看这份。

## 中文版

## 1. 先说结论

### 现在的新订阅和之前的学生订阅是不是一样？

**不完全一样，但功能上很接近。**

相同点：

- 还是 `Azure Container Apps + ACR + Storage + Log Analytics`
- 还是 `swedencentral`
- 还是同一个应用名：`aca-aphid-yolo`
- 还是同一套 API 路由：`/health`、`/predict`、`/telemetry`、`/history`、`/decision/weekly`、`/forecast/weekly`

不同点：

- 订阅变了
- 资源组变了
- ACR 变了
- Storage Account 变了
- Log Analytics Workspace 变了
- 线上 URL 变了
- **旧学生订阅里的历史数据没有自动搬过来**

一句话理解：

**现在是“同样的项目结构，新的 PAYG 环境”。**

## 2. 当前 Azure 环境信息

当前新环境：

- Subscription Name: `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Resource Group: `rg-aphid-yolo-payg`
- Region: `swedencentral`
- Container App: `aca-aphid-yolo`
- Container App URL: `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`
- ACR: `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Log Analytics Workspace: `workspace-rgaphidyolopaygK1ST`

Grafana 用的 Service Principal：

- App Name: `grafana-access-payg`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Role: `Monitoring Reader`
- Scope: 当前整个 PAYG 订阅

注意：

- `Client Secret` **不要写进仓库**
- 我已经把它保存在本地文件里：  
  `C:\Users\Amour\Desktop\grafana-access-payg-credentials.txt`

## 3. Grafana 里现在能查什么

### 现在可以直接查的内容

用 `Azure Monitor` 数据源时，现在可以直接查：

- `Log Analytics` 里的日志
- `Azure Monitor Metrics`
- `Container App` 的平台日志和应用日志

当前工作区里已经确认存在这些常用表：

- `ContainerAppConsoleLogs_CL`
- `ContainerAppSystemLogs_CL`
- `AppRequests`
- `AppTraces`

### 现在不能直接查的内容

下面这两张是 **Azure Table**，不是 `Azure Monitor Logs`：

- `iottelemetry`
- `aphidcounts`

所以：

**Grafana 的 Azure Monitor 数据源现在不能直接查这两张表。**

如果后面要让 Grafana 查这两张业务表，需要再做一层同步，把它们送进 Log Analytics 自定义表。

## 4. Grafana 里怎么填 Azure Monitor 数据源

在 Grafana 的 `Azure Monitor` data source 页面填：

- Authentication: `Service Principal`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Client Secret: 从本地安全文件里取，不要写进仓库
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

然后：

1. 点 `Save & Test`
2. 如果成功，再开始做 Panel

## 5. 最简单的查询方式

### 5.1 查容器控制台日志

在 Grafana 里：

1. 选择数据源：`Azure Monitor`
2. Query type：`Logs`
3. Workspace：`workspace-rgaphidyolopaygK1ST`
4. KQL：

```kusto
ContainerAppConsoleLogs_CL
| order by TimeGenerated desc
| take 20
```

### 5.2 查容器系统日志

```kusto
ContainerAppSystemLogs_CL
| order by TimeGenerated desc
| take 20
```

### 5.3 查最近请求

```kusto
AppRequests
| project TimeGenerated, Name, ResultCode, DurationMs, Success
| order by TimeGenerated desc
| take 20
```

### 5.4 查最近应用 trace

```kusto
AppTraces
| project TimeGenerated, SeverityLevel, Message
| order by TimeGenerated desc
| take 20
```

### 5.5 做一个 5 分钟请求趋势图

```kusto
AppRequests
| summarize request_count = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

## 6. 如果你想查 Metrics

如果你想查 CPU、内存、请求量这类指标：

1. 数据源还是选 `Azure Monitor`
2. Query type 选 `Metrics`
3. Resource type 选 `Microsoft.App/containerApps`
4. Resource 选 `aca-aphid-yolo`
5. 再选你要看的 metric

这条路线适合做：

- 请求数
- 响应趋势
- 资源使用趋势

## 7. 最容易混淆的点

### 混淆点 1：Save & Test 成功，是不是就能查所有数据？

不是。

`Save & Test` 成功，只说明：

- Grafana 能登录 Azure
- 能访问 Azure Monitor

它**不代表**：

- 能直接查 Azure Table

### 混淆点 2：为什么查不到 `iottelemetry` 和 `aphidcounts`？

因为它们现在在 Storage Table 里，不在 Log Analytics 里。

### 混淆点 3：新订阅是不是已经把旧订阅的数据也带过来了？

没有。

这次迁移完成的是：

- 基础设施
- 应用部署
- 存储结构

不是：

- 旧学生订阅里的全部历史数据复制

## 8. 最实用的排查顺序

如果 Grafana 查不到东西，按这个顺序排查：

1. `Save & Test` 是否成功
2. Tenant ID / Client ID / Client Secret / Subscription ID 是否填对
3. Workspace 是否选对：`workspace-rgaphidyolopaygK1ST`
4. Query type 是否选成 `Logs`
5. 时间范围是不是太短
6. 你是不是在查 Azure Table，而不是 Log Analytics 表

## 9. 给 teammate 的一句话

如果你要给 teammate 一个最短说明，可以直接发这段：

> 我们现在已经切到新的 PAYG 订阅了。  
> Grafana 可以直接查 `workspace-rgaphidyolopaygK1ST` 里的 `ContainerAppConsoleLogs_CL`、`ContainerAppSystemLogs_CL`、`AppRequests`、`AppTraces`。  
> 但 `iottelemetry` 和 `aphidcounts` 现在还在 Azure Table 里，不能直接通过 Azure Monitor 数据源查询。

---

## English Version

## 1. The short answer

### Is the new subscription exactly the same as the old student subscription?

**No, not exactly, but it is functionally very similar.**

Same:

- Still uses `Azure Container Apps + ACR + Storage + Log Analytics`
- Still in `swedencentral`
- Still uses the same app name: `aca-aphid-yolo`
- Still exposes the same API routes

Different:

- New subscription
- New resource group
- New ACR
- New storage account
- New Log Analytics workspace
- New public app URL
- **Old historical data was not automatically copied**

Short version:

**It is the same project architecture, but running in a new PAYG environment.**

## 2. Current Azure environment

Current environment:

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

Grafana Service Principal:

- App Name: `grafana-access-payg`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Role: `Monitoring Reader`
- Scope: the whole current PAYG subscription

Important:

- Do **not** commit the client secret into the repo
- The secret is stored locally in:  
  `C:\Users\Amour\Desktop\grafana-access-payg-credentials.txt`

## 3. What Grafana can query right now

### What works now

With the `Azure Monitor` data source, Grafana can currently query:

- `Log Analytics` logs
- `Azure Monitor Metrics`
- Container App platform logs and application logs

These useful tables are already confirmed in the current workspace:

- `ContainerAppConsoleLogs_CL`
- `ContainerAppSystemLogs_CL`
- `AppRequests`
- `AppTraces`

### What does not work directly right now

These two are still stored as Azure Tables:

- `iottelemetry`
- `aphidcounts`

So:

**Grafana Azure Monitor cannot query these Azure Tables directly.**

If you want Grafana to query them later, they must first be synced into Log Analytics custom tables.

## 4. How to fill the Azure Monitor data source in Grafana

Use these values:

- Authentication: `Service Principal`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Client Secret: read it from the local secure file
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

Then:

1. Click `Save & Test`
2. If successful, start creating panels

## 5. The simplest queries

### 5.1 Container console logs

```kusto
ContainerAppConsoleLogs_CL
| order by TimeGenerated desc
| take 20
```

### 5.2 Container system logs

```kusto
ContainerAppSystemLogs_CL
| order by TimeGenerated desc
| take 20
```

### 5.3 Recent requests

```kusto
AppRequests
| project TimeGenerated, Name, ResultCode, DurationMs, Success
| order by TimeGenerated desc
| take 20
```

### 5.4 Recent traces

```kusto
AppTraces
| project TimeGenerated, SeverityLevel, Message
| order by TimeGenerated desc
| take 20
```

### 5.5 Request trend every 5 minutes

```kusto
AppRequests
| summarize request_count = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

## 6. If you want Metrics

For CPU / memory / request-style metrics:

1. Select `Azure Monitor`
2. Set query type to `Metrics`
3. Set resource type to `Microsoft.App/containerApps`
4. Select resource `aca-aphid-yolo`
5. Pick the metric you need

## 7. The most common confusion

### Confusion 1: If Save & Test succeeds, can I query everything?

No.

It only means:

- Grafana can authenticate to Azure
- Grafana can access Azure Monitor

It does **not** mean:

- Grafana can directly read Azure Tables

### Confusion 2: Why can’t I query `iottelemetry` and `aphidcounts`?

Because they are currently in Azure Table Storage, not in Log Analytics.

### Confusion 3: Did the new subscription already include all old data?

No.

What was migrated:

- infrastructure
- application deployment
- storage structure

What was **not** migrated automatically:

- all old historical data from the disabled student subscription

## 8. The practical troubleshooting order

If Grafana returns no data, check in this order:

1. Did `Save & Test` succeed?
2. Are Tenant ID / Client ID / Client Secret / Subscription ID correct?
3. Did you select the correct workspace: `workspace-rgaphidyolopaygK1ST`?
4. Is the query type set to `Logs`?
5. Is the time range too short?
6. Are you trying to query Azure Tables instead of Log Analytics tables?

## 9. One short message for teammates

You can send this to a teammate:

> We have already moved to the new PAYG subscription.  
> Grafana can directly query `ContainerAppConsoleLogs_CL`, `ContainerAppSystemLogs_CL`, `AppRequests`, and `AppTraces` in `workspace-rgaphidyolopaygK1ST`.  
> But `iottelemetry` and `aphidcounts` are still in Azure Table Storage and cannot yet be queried directly through the Azure Monitor data source.
