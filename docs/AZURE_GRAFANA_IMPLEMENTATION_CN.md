# Azure 实施说明：当前真实状态和后续落地步骤

说明：这份文档主要记录旧学生订阅被禁用时的背景。当前 PAYG 订阅请优先看：`docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`

这份文档不是“理论方案”，而是我已经在 Azure 里实际检查过后的真实记录。

适合给两类人看：

- 负责 Azure 资源的人
- 需要知道这件事现在做到哪一步的人

这份文档尽量只说人话，只保留真正有用的信息。

## 1. 先说结论

当前项目如果想让 Grafana 查到温湿度、气压和虫子数量，最合理的 Azure 路线仍然是：

```text
Azure Table -> 同步链路 -> Log Analytics 自定义表 -> Grafana
```

但是，今天我已经实际开始动 Azure 了，结果发现一个现实阻塞：

**当前订阅是 Disabled。**

这意味着：

- 我可以读取资源信息
- 我不能新建或修改 Azure 资源
- 所以目前还不能真的把自定义表建出来

一句话总结就是：

**方向已经确认，环境也核查完了，但 Azure 订阅现在是只读状态，所以实施停在“确认现状”这一步。**

## 2. 我已经实际做了什么

下面这些不是计划，而是我已经实际执行过并确认过的内容。

### 2.1 我确认了当前订阅状态

我实际查到的默认订阅是：

- Subscription: `Azure for Students`
- Tenant: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- State: `Disabled`

这个状态很关键，因为它直接决定了后面能不能写 Azure 资源。

### 2.2 我确认了当前资源组里已经有什么

资源组：

- `rg-aphid-yolo-se`

我已经确认存在这些核心资源：

- Container Registry: `acraphidyolo2498`
- Log Analytics Workspace: `workspace-rgaphidyoloseNxBa`
- Container App Environment: `aca-env-aphid-yolo`
- Container App: `aca-aphid-yolo`
- Storage Account: `staphid25021201`

说明现在的基础资源不是空的，项目本体还在。

### 2.3 我确认了 Workspace 里现在有什么日志

当前 Log Analytics Workspace 里已经有一些平台日志，例如：

- `ContainerAppSystemLogs_CL`
- `ContainerAppConsoleLogs_CL`
- `AppRequests`
- `AppTraces`

这说明：

- Container App 的平台日志链路是有的
- 但这不是我们要给 Grafana 用的业务数据

### 2.4 我确认了现在还没有什么

我已经确认，目前还没有下面这些关键东西：

- `IoTTelemetry_CL`
- `AphidCounts_CL`
- DCR
- DCE
- Azure Table 到 Log Analytics 的同步链路

也就是说，**Grafana 现在就算接上 Azure Monitor，也查不到你真正想看的虫量和温湿压业务数据。**

### 2.5 我已经实际尝试创建自定义表

我不是只做了检查，还真的尝试开始建表了。

我实际尝试创建的是：

- `IoTTelemetry_CL`

Azure 返回的真实错误是：

```text
ReadOnlyDisabledSubscription
The subscription '12190bf7-b4d8-4dfa-9a63-01580c6ad868' is disabled and therefore marked as read only.
You cannot perform any write actions on this subscription until it is re-enabled.
```

这个报错已经说明问题很明确：

- 不是命令写错
- 不是权限少一条普通 RBAC
- 而是订阅本身已经被 Azure 标成只读

## 3. 现在到底卡在哪里

现在卡点很单纯：

**不是架构卡住，也不是代码卡住，而是 Azure 订阅状态卡住。**

只要订阅还是 `Disabled`，我后面这些动作都会失败：

- 新建 Log Analytics 自定义表
- 新建 DCR
- 新建 DCE
- 创建正式同步链路
- 修改任何需要写入 Azure 的配置

所以当前真正的下一步不是“继续写技术实现”，而是：

**先把 Azure 订阅恢复成可写状态。**

## 4. 订阅恢复后，我会怎么继续做

等订阅恢复正常后，我建议按这个顺序继续。

### 第一步：创建两张业务自定义表

目标表名：

- `IoTTelemetry_CL`
- `AphidCounts_CL`

建议字段先固定成下面这样。

`IoTTelemetry_CL`

- `TimeGenerated`
- `device_id_s`
- `temperature_d`
- `humidity_d`
- `pressure_hpa_d`
- `light_d`

`AphidCounts_CL`

- `TimeGenerated`
- `device_id_s`
- `count_d`
- `request_id_s`
- `filename_s`

### 第二步：补齐 Logs Ingestion 需要的 Azure 资源

也就是：

- DCE
- DCR

你可以把它们简单理解成：

- DCE 负责“入口”
- DCR 负责“规则”

### 第三步：做同步链路

最推荐的是做一个定时同步器。

最务实的方式是：

- Azure Function
- Timer Trigger

它做的事很简单：

1. 从 Azure Table 读新数据
2. 整理成目标结构
3. 写入 Log Analytics 自定义表

数据来源还是现在的两张表：

- `iottelemetry`
- `aphidcounts`

### 第四步：验证数据真的能查

验证一定不要省。

至少要能在 Workspace 里直接跑出这些查询：

```kusto
IoTTelemetry_CL
| take 10
```

```kusto
AphidCounts_CL
| take 10
```

### 第五步：再交给 Grafana teammate

到这一步之后，再让 teammate 去做 Grafana 才是顺的。

到时候我需要交给他：

- Workspace 名称
- 最终表名
- 字段清单
- 一两条 KQL 示例
- 数据同步频率

## 5. 为什么我还是推荐这条 Azure 路

虽然今天被订阅状态卡住了，但路线本身没有变。

我还是推荐这条路，是因为：

- 你现在业务数据本来就在 Azure Table
- Grafana 那边本来就想走 Azure Monitor
- 把业务数据同步到 Log Analytics 后，Grafana 侧会标准很多
- teammate 后面只需要写 KQL，不用管 Azure Table 细节

所以今天的结论不是“路线错了”，而是：

**路线对，但 Azure 订阅现在不可写。**

## 6. 给 teammate 的一句话版本

如果你只想把事情讲给 teammate 听，可以直接说：

> 我这边已经确认好 Azure 路线了，目标是把 `iottelemetry` 和 `aphidcounts` 同步到 Log Analytics 的 `IoTTelemetry_CL` 和 `AphidCounts_CL`，然后让你在 Grafana 用 Azure Monitor Logs 查。  
> 但 Azure 订阅目前是 `Disabled`，所以表还没真的建出来。等订阅恢复后，我会先把表和同步链路补好，再把表名和 KQL 给你。

## 7. 当前最重要的下一步

当前最重要的事情不是再写文档，也不是再讨论字段名，而是：

**让 Azure 订阅恢复为可写状态。**

只要这一步没完成，Azure 侧实施就无法继续往前推。

## 8. 最后一句话

今天这轮工作的真实结果是：

- 架构路线已经确认
- Azure 当前资源现状已经核实
- 真正阻塞点已经定位
- 但 Azure 订阅现在是只读，导致实施暂时停住

所以这份文档的核心价值不是“讲理想方案”，而是把当前真实状态讲清楚，避免团队误以为自定义表已经建好了。
