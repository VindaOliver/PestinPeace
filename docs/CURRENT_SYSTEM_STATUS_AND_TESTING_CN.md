# 当前系统状态与测试结论

这份文档用来回答 3 个最实际的问题：

1. 现在系统部署在哪里
2. 现在系统哪些功能已经可用
3. 最近一次优化和测试做到什么程度

## 1. 当前运行环境

当前正式运行环境是 Azure PAYG。

线上地址：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

当前主资源：

- Resource Group: `rg-aphid-yolo-payg`
- Container App: `aca-aphid-yolo`
- Storage Account: `staphidpayg9547`
- ACR: `acraphidyolo9547`

## 2. 当前系统已经能做什么

### 图像识别

- `POST /predict`
- 现在 `device_id` 是必填
- 单次识别按单张图片模式记录
- 返回：
  - `count`
  - `detections`
  - `count_mean`
  - `images_in_round`
  - `aggregation_mode`

### 传感器数据

- `POST /telemetry`
- `GET /telemetry/latest`
- `GET /grafana/telemetry`

当前环境数据字段已经支持：

- `ts_utc`
- `round_id`
- `lux_avg`
- `lux_valid`
- `env_valid`
- `temperature_c`
- `pressure_hpa`
- `humidity_pct`
- `soil_valid`
- `soil_raw`
- `soil_moisture_pct`
- `fill_on`
- `shots_planned`

### 虫量数据

- `GET /grafana/aphidcounts`
- `GET /predict/trend`

当前虫量接口支持：

- `round_id`
- `count`
- `count_mean`
- `images_in_round`
- `aggregation_mode`

### 决策历史

- `POST /decision/history`
- `GET /decision/history`
- `GET /grafana/decisionhistory`

可以直接判断：

- `last_uploaded_record_is_spray`
- `last_uploaded_record_should_spray`

### 每周预测与决策

- `POST /forecast/weekly`
- `GET /forecast/auto`
- `POST /decision/weekly`

## 3. Dashboard 入口

这些路由当前都已经可访问：

- `/predict/dashboard`
- `/telemetry/dashboard`
- `/history/dashboard`
- `/decision/dashboard`
- `/forecast/dashboard`

## 4. 当前 Grafana 方案

现在 Grafana 的业务数据主线是：

`Grafana -> API -> Azure Table`

也就是说：

- 不再用旧的 Log Analytics 业务同步方案做主链路
- Grafana 主要查：
  - `/grafana/telemetry`
  - `/grafana/aphidcounts`
  - `/grafana/decisionhistory`

## 5. 最近一次高优先级优化

为了让系统更稳，这一轮已经完成这些修复：

1. `/predict` 现在强制要求 `device_id`
2. 预测页面会主动传 `device_id`
3. `/predict` 的 `conf / iou / imgsz / max_det` 增加了边界校验
4. Azure Table 写入和查询增加了重试
5. Open-Meteo 天气请求增加了重试
6. `/history` 的 blob 列表增加了重试
7. 新增 `/ready`
8. `/ready` 在 not ready 时会返回 `503`
9. 增加了模型加载守卫
10. `/history` 单条 blob 读取失败时会记录 warning
11. 重试退避改成了指数退避

## 6. 最近一次测试结果

### 本地测试

本地 smoke test：

- `20/20` 通过

### 线上测试

远程 smoke test：

- `13/13` 通过

关键线上行为确认：

- `/ready`：`200`
- `/health`：`200`
- `/predict` 不带 `device_id`：`422`
- `/predict?conf=-1`：`422`
- `/predict?imgsz=99999`：`422`
- 正常图片识别：`200`

## 7. GitHub 与 Azure 自动部署状态

当前 `main` 分支 push 后会自动部署到 Azure。

最近几次成功运行包括：

- `24759555774`
- `24759829225`
- `24760621732`

说明：

- GitHub Actions 已正常
- Azure Container App 自动部署已正常
- Weekly decision / forecast smoke test 已随部署流程一起跑通

## 8. 当前结论

如果按课程项目 / 小组答辩标准看：

**现在这套系统已经可以正常演示和使用。**

如果按长期稳定运行标准看：

还有一些非阻塞优化可以继续做，但已经没有高严重级别问题。

## 9. 目前剩余的非阻塞优化

当前还值得继续做，但不会阻塞答辩的点主要有：

1. `/history` 逐个 blob 下载也可以再加重试
2. 真实生产环境里可以收紧 CORS 配置
3. 如果后面长期运行，可以再统一错误响应格式

## 10. 给队友的一句话版本

当前系统已经稳定切到 PAYG，主链路可用，自动部署可用，Grafana 现在通过 API 读取业务数据，答辩和演示使用没有问题。

## 11. 答辩材料放在哪里

当前最适合答辩直接使用的资料已经整理在：

- `defense_assets/README_CN.md`

重点包括：

- Azure 架构图
- YOLO 训练结果图和指标
- 当前 PAYG 部署摘要
- 演示用 sample data
