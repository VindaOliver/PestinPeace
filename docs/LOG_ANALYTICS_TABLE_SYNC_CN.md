# Azure Table 到 Log Analytics 同步说明

这份文档说明我们现在怎么把 Azure Table 里的两张业务表同步进 Log Analytics 自定义表，方便后面给 Grafana 和 KQL 查询用。

## 1. 现在同步的是哪两张源表

- `iottelemetry`
- `aphidcounts`

它们都还在 Storage Account `staphidpayg9547` 的 Azure Table 里。

## 2. 同步到哪两张目标表

同步进 Log Analytics Workspace `workspace-rgaphidyolopaygK1ST` 里的两张自定义表：

- `IoTTelemetry_CL`
- `AphidCounts_CL`

后缀 `_CL` 是 Log Analytics 自定义表的标准做法。

## 3. 这条同步链路现在怎么工作

现在我们走的是 Azure 官方推荐的 Logs Ingestion API 路线。

整体流程是：

1. Azure Table 里原始业务数据继续照常写入。
2. GitHub Actions 定时运行同步任务。
3. 同步脚本从 Azure Table 读取新增行。
4. 脚本通过 DCR 把数据送进 Log Analytics 自定义表。
5. Grafana 和 Log Analytics 查询改查 `IoTTelemetry_CL`、`AphidCounts_CL`。

## 4. 仓库里对应的文件

- DCR 模板  
  [infra/azure/log_analytics_table_sync_dcr.template.json](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/infra/azure/log_analytics_table_sync_dcr.template.json)

- Azure 侧初始化脚本  
  [scripts/deploy/setup_log_analytics_table_sync.ps1](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/scripts/deploy/setup_log_analytics_table_sync.ps1)

- 实际同步脚本  
  [scripts/sync/sync_azure_tables_to_log_analytics.py](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/scripts/sync/sync_azure_tables_to_log_analytics.py)

- GitHub Actions 定时任务  
  [sync_log_analytics_tables.yml](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/.github/workflows/sync_log_analytics_tables.yml)

## 5. 这条同步现在会不会重复写

不会直接每次全量重写。

脚本会在 Storage Account 里维护一个检查点表：

- `loganalyticssyncstate`

它会记录每张源表上次同步到哪里了，所以后续只同步新增的行。

## 6. 同步完成后怎么查

### 6.1 在 Azure Portal 里查

进入 Log Analytics Workspace，然后运行 KQL：

```kusto
IoTTelemetry_CL
| sort by TimeGenerated desc
| take 20
```

```kusto
AphidCounts_CL
| sort by TimeGenerated desc
| take 20
```

### 6.2 在 Grafana 里查

前提是 Grafana 的 Azure Monitor data source 已经配置好。

之后就可以在 Logs 查询里直接写：

```kusto
IoTTelemetry_CL
| where DeviceId == "pi-001"
| sort by TimeGenerated desc
| take 50
```

```kusto
AphidCounts_CL
| where DeviceId == "pi-001"
| sort by TimeGenerated desc
| take 50
```

## 7. 如果我要手动跑一次同步

先 Azure 登录，然后运行：

```powershell
pwsh .\scripts\deploy\setup_log_analytics_table_sync.ps1
```

然后再运行同步脚本。

如果你是在 GitHub Actions 里跑，一般不需要手动干预，因为 workflow 会自动处理。

## 8. 这个方案的现实边界

- 现在同步的是 Azure Table -> Log Analytics，不是实时流式毫秒级同步。
- 对小组作业和 dashboard 展示，这已经够用。
- 如果后面数据量变大，再考虑改成更强的流式架构。
