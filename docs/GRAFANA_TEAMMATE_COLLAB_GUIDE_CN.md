# Grafana 协作文档：现在做到哪一步，以及你接下来怎么配合

当前 PAYG 订阅请优先看：`docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`

这份文档是直接给 teammate 看的。

它只回答 4 个问题：

- 现在做到哪一步了
- 你这边什么时候能开始做 Grafana
- 你后面具体查哪两张表
- 如果没数据，先怀疑什么

## 1. 先说现在的真实状态

我这边已经开始动 Azure 了，也已经把路线确认好了。

目标路线是：

```text
Azure Table -> Log Analytics 自定义表 -> Grafana
```

原始数据来源还是项目里现在这两张 Azure Table：

- `iottelemetry`
- `aphidcounts`

后面准备同步到 Log Analytics 的两张表是：

- `IoTTelemetry_CL`
- `AphidCounts_CL`

但是现在有一个真实阻塞：

**Azure 订阅当前是 `Disabled`。**

这会导致 Azure 资源只能读，不能写。

所以请注意：

**现在这两张自定义表还没有真正建出来。**

## 2. 这意味着什么

这意味着两件事：

### 第一件事

路线已经定了，不会改成别的奇怪方案。

后面你在 Grafana 里还是会查：

- `IoTTelemetry_CL`
- `AphidCounts_CL`

### 第二件事

你现在如果马上去 Grafana 里写 KQL，很可能查不到数据。

原因不是你不会写，也不是 Grafana 坏了，而是：

**Azure 这边的目标表还没创建成功。**

## 3. 我这边负责什么

我负责把 Azure 这条链路先打通。

简单说，我负责：

1. 把自定义表建出来
2. 把 Azure Table 里的业务数据同步进去
3. 确认表里真的有数据
4. 再把最终表名和示例 KQL 给你

## 4. 你这边现在不用做什么

你现在不用去做这些事：

- 不用直接碰 Azure Table
- 不用猜字段名
- 不用硬写一堆 KQL 去试
- 不用怀疑 Grafana 为什么查不到业务数据

因为当前阻塞不是你这边造成的。

## 5. 你这边什么时候开始最合适

最合适的时机是：

**等我明确告诉你下面这 4 件事之后，你再开始正式做 Grafana。**

我会告诉你：

1. `IoTTelemetry_CL` 已经建好
2. `AphidCounts_CL` 已经建好
3. 两张表已经有真实数据
4. 可以直接复制的 KQL 示例

到那时候，你再开始做图，会顺很多。

## 6. 你后面最终会查哪两张表

后面如果 Azure 恢复正常，你在 Grafana 里主要查这两张表。

### 环境数据表

```text
IoTTelemetry_CL
```

预计字段：

- `TimeGenerated`
- `device_id_s`
- `temperature_d`
- `humidity_d`
- `pressure_hpa_d`
- `light_d`

### 虫量数据表

```text
AphidCounts_CL
```

预计字段：

- `TimeGenerated`
- `device_id_s`
- `count_d`
- `request_id_s`
- `filename_s`

如果字段有微调，我会重新告诉你，不会让你自己猜。

## 7. 你后面在 Grafana 里怎么接

等我这边确认“表和数据都已经到位”之后，你在 Grafana 里只要按这个最简单流程走：

1. 打开 Grafana
2. 选择数据源 `Azure Monitor`
3. 查询类型选 `Logs`
4. 选对应的 Log Analytics Workspace
5. 粘贴 KQL
6. 开始做图

对你来说，事情就保持这么简单。

## 8. 你最先应该做的 4 张图

我建议你后面先做最基础的 4 张图，不要一开始就搞很复杂的 dashboard。

先做：

1. 温度时间曲线
2. 湿度时间曲线
3. 气压时间曲线
4. 每天虫量变化图

这 4 张出来，就已经足够证明整条链路跑通了。

## 9. 后面我会直接给你的 KQL 类型

等表真的建好后，我会直接给你这种能复制就用的 KQL。

例如温度图会长这样：

```kusto
IoTTelemetry_CL
| where device_id_s == "trap-001"
| project TimeGenerated, temperature_d
| order by TimeGenerated asc
```

例如每天虫量图会长这样：

```kusto
AphidCounts_CL
| where device_id_s == "trap-001"
| summarize aphid_count = sum(count_d) by bin(TimeGenerated, 1d)
| order by TimeGenerated asc
```

你不用现在就记这些，知道后面会直接给你可复制版本就行。

## 10. 如果你现在去查不到数据，先怎么理解

如果你现在就去 Grafana 里试，很可能会遇到空结果。

这个时候先这样理解：

- 不是你查错了
- 不是 Grafana 一定坏了
- 更大的可能是 Azure 订阅还没恢复，所以业务表根本还没创建成功

所以当前阶段最重要的不是“改查询”，而是“等 Azure 恢复可写”。

## 11. 我们最省事的协作方式

为了不来回猜，最省事的协作方式是这样的。

### 我负责告诉你

- 表有没有真的建好
- 数据有没有真的进来
- 最终字段名是什么
- 哪个 `device_id` 用来测试
- 哪些 KQL 可以直接复制

### 你负责告诉我

- 哪张图你想先做
- 你更想按小时看，还是按天看
- 哪条 KQL 报错或没数据

## 12. 最后一句话

你现在可以把事情想得非常简单：

**现在不是你不会做 Grafana，而是 Azure 这边还没恢复到可写状态。**

等我把 Azure 侧这一步打通后，你那边的工作就会变成：

**选 Azure Monitor、贴 KQL、出图。**
