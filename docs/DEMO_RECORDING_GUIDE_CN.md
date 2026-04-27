# 演示视频录制指南

这份文档是给录制演示视频用的。推荐使用新页面：

`/demo/dashboard`

线上地址：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/demo/dashboard`

## 录制前准备

1. 准备一张虫子比较清楚的图片。
2. 打开 `/demo/dashboard`。
3. `device_id` 建议先用 `demo-trap-001`。
4. 先点“检查 /health + /ready”，把服务唤醒。
5. 如果录制时必须展示真实硬件，可以把 `device_id` 改成 `pi-001`，但 Grafana 里可能会有不少空字段。

## 推荐录制顺序

1. 检查服务状态。
2. 上传一轮传感器数据。
3. 上传图片并识别 aphid / slug。
4. 查看虫量趋势和自动预测。
5. 触发喷药建议。
6. 保存喷药决策历史。
7. 刷新 Grafana API 数据，证明三类数据都能查回。

## 建议讲解词

可以按这个顺序讲：

> 首先硬件上传温湿度、气压、光照和土壤湿度等环境数据。

> 然后摄像头拍照，图片送到 YOLO 模型识别 aphid 和 slug，系统保存虫量和检测框。

> 接着系统读取历史虫量和最近环境数据，并结合伦敦天气预测未来虫量趋势。

> 最后喷药决策接口根据虫量、面积和环境条件，给出是否喷药、喷药范围和用量建议，并把本次喷药记录写入历史。

## 为什么不用纯随机现场数据

录视频最怕现场拍出来虫子太少，导致模型不给喷药建议。

所以推荐做法是：

- 图片识别可以现场真实上传。
- 趋势和 Grafana 演示使用 `demo-trap-001` 的完整演示数据。
- 喷药决策使用页面默认的 `aphid_count=25`，这样稳定触发 `should_spray=true`。
- 喷药面积使用页面默认的 `field_area_ha=0.00008`，也就是 0.8 平方米，避免演示时出现大田级别的喷药量。
- 喷头使用 Hunter MP1000 的默认换算：`90° arc + 40 PSI + 0.21 GPM`，约 `13.25 ml/s`。页面会显示 `nozzle.runtime_sec`；0.8 平方米边界喷施约 `8.4 ml / 0.6 s`，高风险全区喷施约 `40 ml / 3.0 s`，录制时推荐展示更容易看清的全区喷施场景。

这不是造假，而是录制一个稳定的端到端演示场景：重点展示系统链路是否打通。

## 视频里建议展示的结果

- `/predict` 返回 `aphid_count`、`slug_count`、`total_count`
- `/forecast/auto` 返回趋势标签和下一阶段估计数量
- `/decision/weekly` 返回 `should_spray=true`
- `/decision/weekly` 返回 `product_g`、`spray_ml` 和 `nozzle.runtime_sec`
- `/decision/history` 返回最新一次 `spray_applied=true`
- `/grafana/telemetry`、`/grafana/aphidcounts`、`/grafana/decisionhistory` 都有数据
