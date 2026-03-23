# Aphid Forecast API Usage

这份手册是给第一次接手这个接口的人看的。

目标只有一个：让你不用先看代码，也能明白这套接口怎么用、数据从哪里来、预测结果该怎么理解。

## 1. 先用一句话理解这套系统

这套系统分成两层：

1. 图片识别层
   - 负责识别一张图片里有多少只蚜虫

2. 趋势预测层
   - 负责根据最近几天的虫量变化、温度、湿度、气压，再结合未来天气，判断虫量接下来更可能上升、下降还是持平

所以：

- `/predict` 是“识别虫子”
- `/forecast/auto` 是“判断趋势”

这两个接口不是重复做同一件事，而是前后配合。

## 2. 最重要的结论

如果你现在只想知道“这套东西该怎么用”，记住下面这 4 句话就够了：

1. 传感器数据上传到 `/telemetry`
2. 图片识别上传到 `/predict`
3. `/predict` 会顺手把虫量写进 Azure Table
4. `/forecast/auto` 会自动读取最近几天的历史数据，再结合伦敦天气预报做趋势预测

## 3. 这套系统里有哪些主要接口

### 3.1 `/telemetry`

作用：

- 上传环境传感器数据
- 主要包括温度、湿度、气压

### 3.2 `/predict`

作用：

- 上传图片做虫子识别
- 返回识别到的虫子数量和框选结果
- 同时把这次识别出的虫量写进 Azure Table

### 3.3 `/forecast/weekly`

作用：

- 手工预测接口
- 适合你已经自己准备好了虫量和天气数据，想直接喂给模型

### 3.4 `/forecast/auto`

作用：

- 自动预测接口
- 适合真实运行时使用
- 服务端自己去 Azure 读最近几天的数据，再去拿伦敦天气预报，然后自动生成预测结果

## 4. 这套系统是怎么工作的

如果按真实使用流程来讲，大概是这样：

1. 设备持续上传温度、湿度、气压到 `/telemetry`
2. 用户或设备上传图片到 `/predict`
3. `/predict` 返回这张图识别到多少只蚜虫
4. `/predict` 同时把这次虫量保存到 Azure Table
5. 当你需要判断趋势时，调用 `/forecast/auto`
6. `/forecast/auto` 自动去读取最近几天的环境数据和虫量历史
7. `/forecast/auto` 再去拿伦敦未来几天的天气预报
8. 最后模型返回：
   - `up`
   - `stable`
   - `down`

你可以把它理解成：

- 前面的接口负责“记录现实”
- 后面的接口负责“判断未来趋势”

## 5. 数据到底存在哪里

这是最容易搞混的地方，所以单独说明。

### 5.1 温湿度气压是一张表

环境传感器数据存在 Azure Table：

- 表变量名：`TELEMETRY_TABLE`
- 默认表名：`iottelemetry`

里面主要放：

- `temperature`
- `humidity`
- `pressure_hpa`
- `ts`
- `device_id`

### 5.2 虫子数量是另一张表

虫量数据也存在 Azure Table，但不是同一张表：

- 表变量名：`APHID_COUNT_TABLE`
- 默认表名：`aphidcounts`

里面主要放：

- `count`
- `ts`
- `device_id`
- `request_id`
- `filename`

### 5.3 这两张表不是一张表

这点非常重要：

- 温湿度气压在 `iottelemetry`
- 虫量在 `aphidcounts`

也就是说，现在系统是“分表存储”，不是把所有内容混在一张表里。

这样做的好处是：

- 结构更清晰
- 传感器和识别可以独立运行
- 后续查数据也更方便

## 6. `device_id` 为什么重要

`device_id` 可以理解成：

- 哪一台设备
- 哪一个诱虫板
- 哪一个监测点

自动预测接口会按 `device_id` 去找最近几天的数据。

所以最好保持下面三件事都用同一个 `device_id`：

1. `/telemetry`
2. `/predict`
3. `/forecast/auto`

例如都用：

```text
trap-001
```

这样系统才知道：

- 这几天的温湿压是谁的
- 这几天的虫量是谁的
- 预测应该基于哪一个监测点来做

## 7. 现在是不是“拍照完马上去读传感器”

不是。

当前系统的实际逻辑是：

- 图片识别走 `/predict`
- 传感器数据走 `/telemetry`
- 这两条链路目前是分开的

然后到预测的时候，`/forecast/auto` 再去 Azure Table 里读取“之前已经存好的”最近几天历史数据。

所以它不是：

- 拍一张照
- 当场立刻去测一次温湿度
- 再马上预测

它更像是：

- 平时一直在积累图片识别记录
- 平时一直在积累传感器记录
- 需要判断趋势时，再把这些历史信息拿出来统一分析

## 8. 自动预测接口到底做了什么

自动预测接口是：

```text
GET /forecast/auto
```

假设你调用：

```text
GET /forecast/auto?device_id=trap-001&days=7
```

那它会这样工作：

1. 看当前时间
2. 向前回看 7 天
3. 从 `iottelemetry` 里拿最近 7 天的温度、湿度、气压
4. 计算最近 7 天的平均值
5. 从 `aphidcounts` 里拿最近 7 天的虫量记录
6. 再拿更前面的一个对比窗口，判断最近虫量是在变多还是变少
7. 去获取伦敦未来几天的天气预报
8. 把“最近历史 + 未来天气”一起送进预测模型
9. 返回趋势结果

## 9. 自动预测接口为什么要看“前一个窗口”

因为只看“现在有多少虫”还不够。

比如：

- 这周有 10 只虫

这本身不能说明它是在变好还是变坏。

但如果系统知道：

- 上一周平均每天 1 只
- 这一周平均每天 3 只

那它就能看出来：最近在上升。

所以接口内部不只是看当前窗口，还会看前一个窗口，用来判断趋势方向。

## 10. 未来天气在里面起什么作用

未来天气不是拿来“代替”历史数据的，而是拿来“修正趋势判断”的。

简单理解：

- 如果最近虫量已经在上涨
- 同时未来天气更适合虫子活动
- 那模型会更倾向于判断 `up`

反过来：

- 如果最近虫量在下降
- 同时未来天气也不利于虫子发展
- 那模型会更倾向于判断 `down`

所以这个接口不是只看历史，也不是只看天气，而是两者一起看。

## 11. 自动模式什么时候适合用

自动模式最适合真实运行场景：

- 数据已经在 Azure 里持续积累
- 你不想每次手工整理输入
- 你只想给一个 `device_id`
- 然后让系统自动判断趋势

这时候优先使用：

```text
GET /forecast/auto
```

## 12. 手工模式什么时候适合用

手工模式适合下面几种情况：

- 你在做实验
- 你想手动测试某组天气条件
- 你还没有接好 Azure
- 你想快速验证模型行为

这时候用：

```text
POST /forecast/weekly
```

你自己把这些数字传进去：

- 当前虫量
- 当前温度
- 当前湿度
- 当前气压
- 未来天气

## 13. 快速上手流程

如果你要把这套系统真正用起来，最推荐顺序是：

1. 设备持续上传环境数据到 `/telemetry`
2. 图片持续上传到 `/predict?device_id=<same-id>`
3. 系统自动把虫量写入 `aphidcounts`
4. 需要看趋势时，调用 `/forecast/auto?device_id=<same-id>&days=7`
5. 根据结果判断是否要进一步做管理决策

这是最符合当前系统设计的使用方式。

## 14. 接口示例

### 14.1 上传传感器数据

```bash
curl -X POST "https://<your-app>/telemetry" \
  -H "Content-Type: application/json" \
  -d "{
    \"device_id\": \"trap-001\",
    \"temperature\": 18.4,
    \"humidity\": 67.2,
    \"pressure_hpa\": 1012.1
  }"
```

### 14.2 上传图片识别

```bash
curl -X POST "https://<your-app>/predict?device_id=trap-001" \
  -F "image=@leaf.jpg"
```

### 14.3 自动预测

```bash
curl "https://<your-app>/forecast/auto?device_id=trap-001&days=7"
```

### 14.4 手工预测

```bash
curl -X POST "https://<your-app>/forecast/weekly" \
  -H "Content-Type: application/json" \
  -d "{
    \"aphid_count\": 12,
    \"exposure_days\": 7,
    \"week_start\": \"2026-03-23\",
    \"prev_catch_rate\": 1.10,
    \"t_mean\": 18.2,
    \"rh_mean\": 67.5,
    \"pressure_mean\": 1011.8,
    \"t_forecast\": 21.4,
    \"rh_forecast\": 72.0,
    \"pressure_forecast\": 1008.4,
    \"forecast_source\": \"manual_demo\"
  }"
```

## 15. 结果怎么看

接口返回后，最值得先看的字段是：

- `trend_label`
- `trend_confidence`
- `next_count_estimate`
- `warnings`
- `data_quality`

### 15.1 `trend_label`

含义最直白：

- `up`：更可能上升
- `stable`：变化不大
- `down`：更可能下降

### 15.2 `trend_confidence`

表示这次判断有多确定。

数值越高，说明模型越有把握。

但要注意：

- 高置信度不等于 100% 正确
- 低置信度时更应该把结果当“预警”而不是“结论”

### 15.3 `next_count_estimate`

这是对下一阶段虫量的估计值。

它的作用是帮助你理解趋势的大概强弱，不是承诺未来一定会出现这个精确数字。

### 15.4 `warnings`

这里会告诉你本次结果有什么限制。

例如：

- 最近数据太少
- 上一个对比窗口没有数据
- 天气预报获取失败，改用保守回退方案

### 15.5 `data_quality`

通常是：

- `ok`
- `sparse`

如果是 `sparse`，意思不是接口坏了，而是这次可用数据不够完整，结果更适合作为参考。

## 16. 一个最常见的理解方式

如果接口返回：

```json
{
  "trend_label": "up",
  "trend_confidence": 0.72,
  "next_count_estimate": 15,
  "data_quality": "ok"
}
```

可以理解成：

- 最近这段时间虫量表现和环境情况结合起来看
- 再加上未来天气
- 模型觉得接下来更可能继续上升
- 而且这次用到的数据还算完整

如果返回：

```json
{
  "trend_label": "up",
  "trend_confidence": 0.58,
  "data_quality": "sparse"
}
```

更合理的理解是：

- 模型倾向于认为会上升
- 但数据不够完整
- 这次结果适合作为提醒，不适合直接当成强结论

## 17. 常见问题

### 17.1 这个接口会重新识别图片吗

不会。

真正识别图片的是 `/predict`。

`/forecast/auto` 只是读取已经保存好的历史虫量和传感器数据，再做趋势分析。

### 17.2 它会在拍照后自动读取一次传感器吗

不会。

当前版本里：

- `/predict` 和 `/telemetry` 是分开的
- 预测时使用的是 Azure 中已经存在的历史数据

### 17.3 温湿度和虫量是不是在同一张表里

不是。

当前是分成两张表：

- `iottelemetry`
- `aphidcounts`

### 17.4 如果我不传 `device_id` 会怎样

系统仍然能运行，但虫量会写到 `default` 分区。

这适合临时测试，不适合长期正式使用。

### 17.5 这个接口能不能完全替代人工判断

不能。

它更适合做：

- 趋势预警
- 提前准备
- 辅助决策

不适合被理解成“未来一定就是这样”。

## 18. Dashboard

系统里已经提供了 forecast dashboard：

```text
GET /forecast/dashboard
```

页面里有两种使用方式：

1. Manual Forecast
2. Auto from Azure + London Forecast

如果你只是想本地快速试试，直接开 dashboard 最方便。

## 19. 环境变量

### 19.1 Azure 相关

- `AZURE_STORAGE_CONNECTION_STRING`
- `TELEMETRY_TABLE`
- `APHID_COUNT_TABLE`

### 19.2 天气相关

- `OPEN_METEO_FORECAST_URL`
- `FORECAST_LOCATION_NAME`
- `FORECAST_LATITUDE`
- `FORECAST_LONGITUDE`
- `FORECAST_TIMEZONE`
- `WEATHER_REQUEST_TIMEOUT_SEC`

当前默认天气位置是伦敦：

- `FORECAST_LOCATION_NAME = London`
- `FORECAST_LATITUDE = 51.5072`
- `FORECAST_LONGITUDE = -0.1276`
- `FORECAST_TIMEZONE = Europe/London`

## 20. 什么时候需要 Azure 登录

下面这些事通常不需要先登录 Azure：

- 看文档
- 本地改代码
- 本地做 mock 测试

下面这些事通常需要登录 Azure：

1. 检查线上 Table 是否真的写进数据
2. 检查线上环境变量
3. 验证线上容器访问权限
4. 回填历史数据

## 21. 最后给使用者的建议

最推荐的心态是：

- 用 `/predict` 记录现实
- 用 `/forecast/auto` 判断方向
- 用真实后续结果去验证预测

这套接口最擅长的是“提前提醒你风险可能在上升”，而不是“精确承诺未来一定有多少只虫”。
