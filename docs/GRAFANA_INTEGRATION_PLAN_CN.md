# Grafana 接入当前项目的数据方案说明

配套文档：

- Azure 实施说明：
  `docs/AZURE_GRAFANA_IMPLEMENTATION_CN.md`
- 给 teammate 的协作文档：
  `docs/GRAFANA_TEAMMATE_COLLAB_GUIDE_CN.md`

这份文档的目标很简单：

- 说明当前项目的数据到底存在哪里
- 说明为什么 Grafana 的 Azure Monitor 数据源不能直接读到这些业务数据
- 给出当前项目最合适的接入方案

如果你只想先看结论，可以直接看第 1 节和第 6 节。

## 1. 结论先说

当前项目里的核心业务数据主要不在 Azure Monitor 里，而在：

- Azure Table
- Azure Blob

所以：

1. 只完成 Grafana 的 Azure Service Principal 和权限分配
   - 可以让 Grafana 连接 Azure Monitor
   - 但不能直接看到你项目里的虫量和温湿度业务表

2. 如果你想在 Grafana 里看当前项目的真实业务数据
   - 需要额外做一层“数据接入设计”

最关键的一句话是：

**Azure Monitor 数据源能接 Azure Monitor 的数据，但你当前项目的虫量和温湿度数据，主要存的是 Azure Table，不是 Azure Monitor Logs。**

## 2. 当前项目的数据到底在哪里

根据当前项目代码，主要有两张 Azure Table：

### 2.1 环境数据表

- 表名变量：`TELEMETRY_TABLE`
- 默认表名：`iottelemetry`

里面放的是：

- 温度 `temperature`
- 湿度 `humidity`
- 气压 `pressure_hpa`
- 时间 `ts`
- 设备 `device_id`

### 2.2 虫量数据表

- 表名变量：`APHID_COUNT_TABLE`
- 默认表名：`aphidcounts`

里面放的是：

- 虫量 `count`
- 时间 `ts`
- 设备 `device_id`
- 请求号 `request_id`
- 文件名 `filename`

### 2.3 历史识别记录

项目里还有 Blob：

- `aphid-images`
- `aphid-history`

其中 `aphid-history` 里存的是识别历史 JSON。

## 3. 为什么 Azure Monitor 数据源不能直接读它们

Grafana 的 Azure Monitor 数据源官方主要支持这些 Azure 服务：

- Azure Monitor Metrics
- Azure Monitor Logs
- Azure Resource Graph
- Application Insights

也就是说，它面向的是：

- 指标
- 日志
- 资源查询
- 应用监控数据

而不是 Azure Table Storage 里的业务表。

所以即使你完成了：

1. 创建 Service Principal
2. 分配 Monitoring Reader / Reader 权限

Grafana 也只是获得了“访问 Azure Monitor 类数据”的能力，不代表它就能直接查 `iottelemetry` 和 `aphidcounts`。

## 4. 这不代表 Grafana 不能用

Grafana 还是完全可以接你这个项目的数据，只是不能用“Azure Monitor 数据源直接读 Table”这条路。

你现在有 3 条可选路线：

### 方案 A：最快落地

Grafana 通过 API 读取你当前项目自己的接口数据。

简单理解：

- 不是让 Grafana 直接查 Azure Table
- 而是让 Grafana 调你项目自己的 HTTP API

优点：

- 改动最小
- 最适合当前项目
- 不需要先重构 Azure 存储结构

缺点：

- 不是用 Azure Monitor 数据源
- 需要用 Grafana 的 JSON API / Infinity 之类的数据源插件

### 方案 B：最符合“Azure Monitor 数据源”思路

把 Azure Table 里的业务数据同步到 Log Analytics 自定义表，再让 Grafana 用 Azure Monitor Logs 查询。

简单理解：

- 现在数据在 Table
- Grafana 想查 Logs
- 那就加一层同步，把 Table 数据送进 Log Analytics

优点：

- 能继续沿用 Azure Monitor 数据源
- 后续可以直接用 KQL 做 Dashboard

缺点：

- 实现更复杂
- 需要额外的数据同步链路
- 会增加 Azure 侧维护成本

### 方案 C：长期重构型方案

从源头就把业务数据改成发送到更适合可视化和分析的系统，比如：

- Log Analytics
- Azure Data Explorer
- SQL / PostgreSQL / TimescaleDB
- Prometheus / Managed Prometheus

优点：

- 长期更规范
- 对 Dashboard、告警、查询更友好

缺点：

- 改动最大
- 不适合当前阶段立刻落地

## 5. 三个方案里，当前项目最推荐哪个

**当前项目最推荐：方案 A。**

原因很现实：

1. 你现在的业务数据已经稳定写入 Azure Table
2. 项目自己已经有 API 层
3. Grafana 最终只是要“看图表”
4. 当前最重要的是先把图表跑起来，而不是先重构存储架构

所以最实用的路线是：

- 短期：方案 A，先让 Grafana 能看到数据
- 中期：如果你坚持用 Azure Monitor 数据源，再补方案 B

## 6. 当前项目的最佳接入方案

### 6.1 推荐目标

让 Grafana 展示下面这些内容：

1. 温度时间序列
2. 湿度时间序列
3. 气压时间序列
4. 每天 / 每小时虫量变化
5. 最近 7 天虫量趋势
6. 预测结果与真实结果对比

### 6.2 最适合的接法

Grafana 不直接查 Azure Table，而是查项目 API。

换句话说：

- Azure Table 继续做数据存储
- FastAPI 继续做数据访问层
- Grafana 只负责图表可视化

这条路线最符合当前项目现状。

## 7. 当前项目还缺什么

如果按“Grafana 读取项目 API”这条路线走，当前项目还缺一件事：

**缺面向 Grafana 的聚合接口。**

虽然现在项目里已经有：

- `/telemetry/latest`
- `/history`
- `/predict`
- `/forecast/auto`

但它们更偏业务接口，不是专门为 Grafana 图表设计的。

例如：

- `/telemetry/latest` 适合看最近若干条记录
- `/history` 适合看历史记录列表

但 Grafana 更喜欢这种格式：

- 给我某个设备在一段时间里的时间序列
- 给我按小时 / 按天聚合后的结果
- 给我直接适合画图的数据

## 8. 如果按推荐方案做，应该新增什么接口

这里是最建议补的 4 类接口。

### 8.1 遥测时间序列接口

例如：

```text
GET /grafana/series/telemetry?device_id=trap-001&from=...&to=...
```

返回：

- 时间
- temperature
- humidity
- pressure_hpa

适合做：

- 温度折线图
- 湿度折线图
- 气压折线图

### 8.2 虫量时间序列接口

例如：

```text
GET /grafana/series/aphids?device_id=trap-001&from=...&to=...&bucket=1d
```

返回：

- 时间桶
- 总虫量
- 记录次数

适合做：

- 每天虫量柱状图
- 每周虫量趋势图

### 8.3 预测结果接口

例如：

```text
GET /grafana/forecast/latest?device_id=trap-001&days=7
```

返回：

- 当前预测方向
- 置信度
- 预测虫量
- 数据质量

适合做：

- 趋势卡片
- 当前风险状态面板

### 8.4 对比接口

例如：

```text
GET /grafana/compare/prediction-vs-actual?device_id=trap-001
```

返回：

- 某时间段预测值
- 后续真实值

适合做：

- 预测准确度对比图

## 9. 如果你坚持使用 Azure Monitor 数据源，该怎么做

如果你一定想沿用你前面那套：

- Grafana Cloud
- Azure Monitor 数据源
- Service Principal
- Monitoring Reader

那就要走下面这条路：

### 第一步

先完成 Azure 侧认证配置：

1. 创建 Service Principal
2. 记下 Tenant ID / Client ID / Client Secret
3. 给订阅分配权限

### 第二步

建立业务数据同步链路：

- `iottelemetry` -> Log Analytics 自定义表
- `aphidcounts` -> Log Analytics 自定义表

### 第三步

Grafana 使用 Azure Monitor Logs 查询这些自定义表。

### 第四步

在 Grafana 里用 KQL 做面板和 Dashboard。

## 10. 这条“同步到 Log Analytics”的路适合谁

它更适合这些场景：

- 你明确要求所有图表都只用 Azure Monitor 数据源
- 你后续想统一用 KQL
- 你愿意接受更复杂的 Azure 维护工作

如果你现在只是想尽快把图表做出来，这条路不是最佳首选。

## 11. 推荐的实施顺序

这里给你一个最稳的顺序：

### 阶段 1：先做可用

1. 保持当前数据继续写 Azure Table
2. 新增 Grafana 专用 API 聚合接口
3. 用 Grafana 的 API/JSON 数据源先做图表

### 阶段 2：再做标准化

1. 评估是否真的需要 Azure Monitor 数据源统一化
2. 如果需要，再增加 Table -> Log Analytics 同步

### 阶段 3：再做长期优化

1. 评估是否要把业务数据迁移到更适合分析的后端

## 12. 最后一句话判断

如果你问：

**“当前项目最正确的 Grafana 接法是什么？”**

答案是：

**先不要强行让 Azure Monitor 数据源直接读 Azure Table。**

**当前最合理的路线，是让 Grafana 读取项目 API；如果后面必须统一到 Azure Monitor，再增加同步到 Log Analytics 的链路。**

## 13. 参考资料

Grafana 官方 Azure Monitor 数据源文档：

- https://grafana.com/docs/grafana/latest/datasources/azuremonitor/
- https://grafana.com/docs/grafana-cloud/connect-externally-hosted/data-sources/azure-monitor/

这些官方文档说明 Azure Monitor 数据源支持的重点是：

- Metrics
- Logs
- Resource Graph
- Application Insights

并没有把 Azure Table Storage 作为它的直接查询对象。
