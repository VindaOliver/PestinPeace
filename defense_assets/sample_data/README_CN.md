# Sample Data 说明

这个文件夹存放的是为了演示、答辩、Grafana 测试和 API 联调用准备的样本数据。

## 当前文件

- `telemetry_mock_2026-03-21_to_2026-04-21.csv`
  - 环境与设备采集样本数据
  - 时间范围：`2026-03-21` 到 `2026-04-21`
  - 共 `66` 条记录

- `aphidcounts_mock_2026-03-21_to_2026-04-21.csv`
  - 虫子识别数量样本数据
  - 时间范围：`2026-03-21` 到 `2026-04-21`
  - 共 `66` 条记录

- `decisionhistory_mock_2026-03-21_to_2026-04-21.csv`
  - 决策历史样本数据
  - 时间范围：`2026-03-21` 到 `2026-04-21`
  - 共 `8` 条记录

## 演示设备 ID

为了避免和真实设备数据混在一起，这批样本统一使用：

- `demo-trap-001`

## 已经写入 Azure 的表

这批样本已经写入当前 PAYG 环境的 Azure Table：

- `iottelemetry`
- `aphidcounts`
- `decisionhistory`

因此现在可以直接通过项目接口读取：

- `/grafana/telemetry?device_id=demo-trap-001`
- `/grafana/aphidcounts?device_id=demo-trap-001`
- `/decision/history?device_id=demo-trap-001`
- `/grafana/decisionhistory?device_id=demo-trap-001`
- `/predict/trend?device_id=demo-trap-001`

## 识别口径说明

当前系统统一按 **单张图片识别** 口径来解释，不再把一轮数据表述成“5 张图片取平均”。

也就是说：

- `images_in_round = 1`
- `aggregation_mode = single_image`
- `count_mean = count`
- `shots_planned = 1`

这样更符合当前 `/predict` 实际上传一张图片的实现，也更适合答辩时统一口径。

## telemetry 文件字段说明

- `ts_utc`
  - 采集时间，UTC 时间
- `round_id`
  - 一轮采集任务的编号
- `lux_avg`
  - 光照平均值
- `lux_valid`
  - 光照数据是否有效
- `env_valid`
  - 温湿度气压数据是否有效
- `temperature_c`
  - 温度，摄氏度
- `pressure_hpa`
  - 气压，单位 hPa
- `humidity_pct`
  - 相对湿度，百分比
- `soil_valid`
  - 土壤数据是否有效
- `soil_raw`
  - 土壤传感器原始值
- `soil_moisture_pct`
  - 换算后的土壤湿度百分比
- `fill_on`
  - 补光是否开启，`1` 表示开，`0` 表示关
- `shots_planned`
  - 该轮计划拍摄的图片数量

## aphidcounts 文件字段说明

- `ts_utc`
  - 识别发生时间，UTC 时间
- `round_id`
  - 对应的采集轮次编号
- `request_id`
  - 这一轮识别请求的唯一编号
- `device_id`
  - 设备编号，这里统一是 `demo-trap-001`
- `filename`
  - 识别图片文件名
- `count`
  - 识别出的蚜虫数量
- `count_mean`
  - 该轮平均虫量；当前单图模式下与 `count` 相同
- `images_in_round`
  - 当前轮实际参与识别的图片数量
- `aggregation_mode`
  - 聚合方式；当前为 `single_image`
- `image_blob_name`
  - 演示用图片对象名
- `history_blob_name`
  - 演示用历史记录对象名

## decisionhistory 文件字段说明

- `ts_utc`
  - 决策记录时间，UTC 时间
- `device_id`
  - 设备编号
- `decision_id`
  - 决策记录的唯一编号
- `round_id`
  - 对应的采集轮次编号
- `scope_class`
  - 决策类别
  - `0 = no_spray`
  - `1 = boundary_band`
  - `2 = full_field`
- `scope_name`
  - 决策类别名称
- `should_spray`
  - 系统是否建议喷药
- `spray_applied`
  - 实际是否记录为已喷药
- `product_kg`
  - 药剂量
- `spray_l`
  - 喷液量
- `source`
  - 决策来源
- `reason`
  - 决策原因说明
- `notes`
  - 补充备注

## 写入 Azure Table 时的映射

`telemetry_mock_...csv` 写入 `iottelemetry` 时，主要映射如下：

- `lux_avg -> light`
- `temperature_c -> temperature`
- `humidity_pct -> humidity`
- `pressure_hpa -> pressure_hpa`

同时也保留了这些扩展字段：

- `round_id`
- `lux_valid`
- `env_valid`
- `soil_valid`
- `soil_raw`
- `soil_moisture_pct`
- `fill_on`
- `shots_planned`

`aphidcounts_mock_...csv` 写入 `aphidcounts` 时，会写入：

- `device_id`
- `source_device_id`
- `request_id`
- `round_id`
- `ts`
- `filename`
- `count`
- `count_mean`
- `images_in_round`
- `aggregation_mode`
- `image_blob_name`
- `history_blob_name`

`decisionhistory_mock_...csv` 写入 `decisionhistory` 时，会写入：

- `device_id`
- `decision_id`
- `round_id`
- `ts`
- `scope_class`
- `scope_name`
- `should_spray`
- `spray_applied`
- `product_kg`
- `spray_l`
- `source`
- `reason`
- `notes`

## 这批样本的合理性

- `telemetry` 数据是平稳变化的，没有刻意插入异常值
- `aphid count` 数据整体呈现从 `3 月下旬` 到 `4 月下旬` 逐步升高的趋势
- `decision history` 与虫量上升趋势基本一致，前期以不喷药为主，后期逐步出现建议喷药和已喷药记录

这更适合用于：

- Grafana 演示
- API 接口测试
- 决策历史展示
- 答辩展示
