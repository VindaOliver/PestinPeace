# 小组对接 Playbook：前端、硬件、Grafana 如何接入

这份文档给组内同学快速对接用。它不是完整 API 手册，而是告诉大家：

- 前端同学应该调用哪些接口、展示哪些字段。
- 硬件同学应该上传哪些数据、如何和图片识别对齐。
- Grafana 同学应该从哪里取数、不要再走哪些旧方案。
- 录制演示视频时，三个人如何配合完成完整流程。

当前线上 API：

```text
https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io
```

演示推荐统一使用：

```text
device_id=demo-trap-001
```

真实硬件可以使用：

```text
device_id=pi-001
```

> 注意：`pi-001` 可能包含旧硬件上传的不完整数据，所以如果要录视频或做 Grafana 展示，优先用 `demo-trap-001`。

---

## 1. 当前系统一句话解释

系统流程是：

```text
Camera / Raspberry Pi
  -> POST /telemetry 上传温湿度、气压、光照、土壤湿度
  -> POST /predict 上传图片并识别 aphid / slug
  -> Azure Table / Blob 保存数据
  -> /predict/trend 和 /forecast/auto 预测虫压趋势
  -> /decision/weekly 判断是否建议喷药
  -> /decision/history 保存是否喷药的历史记录
  -> Frontend / Grafana 展示数据
```

最重要的规则：

**同学之间统一通过项目 API 对接，不要直接把 Azure Storage key、表连接串、Azure 密钥发给别人。**

---

## 2. 角色分工

| 角色 | 主要负责 | 不建议做 |
|---|---|---|
| 前端同学 | 页面展示、按钮交互、调用 API、展示虫量/趋势/喷药建议 | 不直接读 Azure Table，不改模型权重 |
| 硬件同学 | 采集传感器数据、拍照、上传 telemetry 和 image | 不直接改后端表结构，不只上传一半字段 |
| Grafana 同学 | 用 API 数据源画图、展示 telemetry / pest count / decision history | 不重新接旧 Log Analytics 表同步方案 |
| 后端/API 负责人 | 维护 API、Azure 表、YOLO 推理、预测和喷药决策逻辑 | 不替前端决定页面设计，不替硬件决定传感器接线 |

---

## 3. 给前端同学：应该接哪些接口

### 3.1 页面入口

已内置页面：

```text
/predict/dashboard
/telemetry/dashboard
/history/dashboard
/forecast/dashboard
/decision/dashboard
/demo/dashboard
/demo/dashboard/en
```

说明：

- `/demo/dashboard` 是中文录屏控制台。
- `/demo/dashboard/en` 是英文录屏控制台。
- 如果英文页还没有部署到线上，先本地打开 `apps/web/web_pages/demo_recording_dashboard_en.html`。

### 3.2 前端最常用接口

| 功能 | 接口 | 方法 | 用途 |
|---|---|---|---|
| 服务检查 | `/health`, `/ready` | GET | 判断 API 是否起来 |
| 图片识别 | `/predict` | POST multipart | 上传图片，返回 aphid/slug 数量和检测框 |
| 历史识别 | `/history` | GET | 查看过去识别记录 |
| 虫压趋势 | `/predict/trend` | GET | 最近 7-90 天 aphid 趋势 |
| 自动预测 | `/forecast/auto` | GET | 用历史表格数据 + 伦敦天气自动预测 |
| 手动预测 | `/forecast/weekly` | POST JSON | 手动输入环境和虫量做预测 |
| 喷药建议 | `/decision/weekly` | POST JSON | 判断是否建议喷药、喷多少 |
| 决策历史 | `/decision/history` | GET/POST | 查询或写入喷药记录 |
| Grafana 数据 | `/grafana/*` | GET | 给图表读取原始业务数据 |

### 3.3 图片识别调用例子

```bash
curl -X POST "$BASE_URL/predict?device_id=demo-trap-001&conf=0.25" \
  -F "image=@test.jpg"
```

前端重点显示这些字段：

| 字段 | 前端应该怎么理解 |
|---|---|
| `aphid_count` | aphid 数量，是预测和喷药决策主线 |
| `slug_count` | slug 数量，用于双类展示和 Grafana |
| `total_count` | 总虫量，等于 aphid + slug |
| `class_breakdown` | 类别拆分，例如 `{"aphid": 12, "slug": 1}` |
| `detections` | 每个检测框，包含 `class_name`、`confidence`、bbox |
| `count` | 旧兼容字段，等于 `aphid_count` |

前端不要只显示 `count`，否则会看起来像系统还是单类识别。

### 3.4 喷药建议调用例子

```bash
curl -X POST "$BASE_URL/decision/weekly" \
  -H "Content-Type: application/json" \
  -d '{
    "aphid_count": 25,
    "field_area_ha": 0.00008,
    "exposure_days": 7,
    "t_mean": 18.6,
    "rh_mean": 72.0,
    "apps_so_far": 0,
    "in_tepp_window": 1
  }'
```

面积单位说明：`field_area_ha` 是公顷，`0.00008 ha = 0.8 m²`。当前录制演示统一按 0.8 平方米计算，让高风险全区喷施接近 40 ml / 3 秒。

喷头说明：当前按 Hunter MP1000 Rotator Nozzle 的保守演示规格换算，默认 `90° arc + 40 PSI + 0.21 GPM`，约等于 `13.25 ml/s`。API 先算需要喷多少 `spray_ml`，再输出 `nozzle.runtime_sec` 告诉硬件喷头大约开多久。0.8 平方米边界喷施约 `8.4 ml / 0.6 s`，高风险全区喷施约 `40 ml / 3.0 s`。真实硬件最好再做一次量杯校准，用实测流量覆盖 `SPRAY_NOZZLE_FLOW_GPM`。

前端重点显示这些字段：

| 字段 | 含义 |
|---|---|
| `should_spray` | 是否建议喷药 |
| `scope_name` | 喷药范围，例如 no_spray / boundary_band / full_field |
| `treated_fraction` | 处理比例 |
| `product_kg` / `product_g` | 药剂用量，小面积展示优先看 g |
| `spray_l` / `spray_ml` | 用水量，小面积展示优先看 ml |
| `nozzle.runtime_sec` | Hunter MP1000 估算喷头开启时间，单位秒 |
| `nozzle.flow_ml_sec` | 当前喷头换算流量，默认约 13.25 ml/s |
| `model.source` | 使用模型还是 fallback rule |

---

## 4. 给硬件同学：应该上传什么

硬件端主要做两件事：

1. 上传环境数据：`POST /telemetry`
2. 上传图片识别：`POST /predict`

### 4.1 建议的一轮采集流程

建议一轮采集使用同一个 `round_id`：

```text
round_ + 当前毫秒时间戳
```

例如：

```text
round_1776781497266
```

推荐顺序：

```text
1. 生成 round_id
2. 读取温度、湿度、气压、光照、土壤湿度
3. POST /telemetry
4. 拍照
5. POST /predict
6. 前端或 Grafana 用 round_id / device_id 查看数据
```

### 4.2 telemetry 上传字段

```bash
curl -X POST "$BASE_URL/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "pi-001",
    "round_id": "round_001",
    "temperature_c": 18.6,
    "humidity_pct": 72.0,
    "pressure_hpa": 1012.8,
    "lux_avg": 320.5,
    "lux_valid": 1,
    "env_valid": 1,
    "liquid_configured": 1,
    "liquid_valid": 1,
    "liquid_raw": 1,
    "liquid_has_liquid": 1,
    "soil_valid": 1,
    "soil_raw": 790,
    "soil_moisture_pct": 12.0,
    "fill_on": 0,
    "shots_planned": 1
  }'
```

字段说明：

| 字段 | 是否建议 | 说明 |
|---|---|---|
| `device_id` | 必须 | 设备 ID，例如 `pi-001` |
| `round_id` | 强烈建议 | 用来对齐同一轮传感器和图片 |
| `temperature_c` | 必须 | 温度，摄氏度 |
| `humidity_pct` | 必须 | 湿度百分比 |
| `pressure_hpa` | 强烈建议 | 气压 |
| `lux_avg` | 建议 | 光照 |
| `liquid_configured` | 建议 | 液体传感器是否配置，0/1 |
| `liquid_valid` | 建议 | 液体传感器读数是否有效，0/1 |
| `liquid_raw` | 建议 | 液体传感器原始值；你同学当前示例里 `-1/0/1` |
| `liquid_has_liquid` | 建议 | 是否检测到液体，0/1 |
| `soil_moisture_pct` | 建议 | 土壤湿度 |
| `soil_raw` | 建议 | 土壤传感器原始值 |
| `shots_planned` | 建议 | 本轮计划拍几张照片 |
| `fill_on` | 建议 | 补光灯是否开启，0/1 |

如果硬件同学手里是 CSV，`ts_utc` 对应 API JSON 里的 `ts` 字段，例如 `"ts": "2026-04-27T13:24:40Z"`。Azure 表里最终仍会返回 `ts_utc` 方便 Grafana 使用。

### 4.3 图片上传字段

```bash
curl -X POST "$BASE_URL/predict?device_id=pi-001&conf=0.25" \
  -F "image=@photo.jpg"
```

当前系统口径：

- 当前线上 `/predict` 是一次请求上传一张图片。
- 返回里的 `images_in_round` 目前是 `1`。
- 返回里的 `aggregation_mode` 目前是 `single_image`。
- 如果硬件实际想一轮拍 5 张，当前最稳做法是连续调用 `/predict` 5 次。
- 答辩前不要说“系统已经自动对 5 张取平均”，除非后端新增 batch 聚合接口。

### 4.4 硬件端验收标准

硬件同学完成后应该能证明：

- `POST /telemetry` 返回 `status=ok`。
- `GET /grafana/telemetry?device_id=pi-001&limit=5` 能看到刚上传的数据。
- `POST /predict` 返回 `aphid_count`、`slug_count`、`total_count`。
- 上传的数据尽量不要出现大量 `null`。
- 传感器和图片尽量用同一个 `round_id`。

---

## 5. 给 Grafana 同学：应该怎么取数

### 5.1 当前推荐方式

Grafana 推荐走：

```text
Grafana HTTP/JSON Data Source -> Project API -> Azure Table
```

不要再把业务数据同步到 Log Analytics 后再查。那条路可以做，但对现在的小组项目更复杂、更容易多花钱，也更容易数据不同步。

### 5.2 三个核心数据接口

传感器：

```text
GET /grafana/telemetry?device_id=demo-trap-001&limit=50
```

虫量：

```text
GET /grafana/aphidcounts?device_id=demo-trap-001&limit=50
```

喷药决策：

```text
GET /grafana/decisionhistory?device_id=demo-trap-001&limit=20
```

带时间范围：

```text
/grafana/telemetry?device_id=demo-trap-001&from=2026-03-21T00:00:00Z&to=2026-04-21T23:59:59Z&limit=500
```

### 5.3 建议做的 Grafana 面板

| 面板 | 接口 | X 轴 | Y 轴 |
|---|---|---|---|
| Temperature | `/grafana/telemetry` | `ts_utc` | `temperature_c` |
| Humidity | `/grafana/telemetry` | `ts_utc` | `humidity_pct` |
| Pressure | `/grafana/telemetry` | `ts_utc` | `pressure_hpa` |
| Soil Moisture | `/grafana/telemetry` | `ts_utc` | `soil_moisture_pct` |
| Aphid Count | `/grafana/aphidcounts` | `ts_utc` | `aphid_count` |
| Slug Count | `/grafana/aphidcounts` | `ts_utc` | `slug_count` |
| Total Pest Count | `/grafana/aphidcounts` | `ts_utc` | `total_count` |
| Spray Decision | `/grafana/decisionhistory` | `ts_utc` | `should_spray` 或 `spray_applied` |

---

## 6. 录制演示视频时的推荐流程

推荐用演示控制台录：

```text
/demo/dashboard
```

英文录制用：

```text
/demo/dashboard/en
```

录制时按这个顺序：

1. 点击 `Check /health + /ready`，证明服务已启动。
2. 点击 `Upload Telemetry`，证明传感器数据进入系统。
3. 选择一张虫子图片，点击 `Upload and Detect`，展示 aphid/slug 数量和检测框。
4. 点击 `Load Trend + Forecast`，展示历史趋势和未来预测。
5. 点击 `Calculate Spray Recommendation`，展示是否建议喷药、喷药范围和用量。
6. 点击 `Save Decision History`，把喷药建议写入历史。
7. 点击 `Refresh Grafana API Data`，证明 telemetry、pest count、decision history 都能查回来。

建议录制讲解词：

> Our device first uploads environmental data, including temperature, humidity, pressure, light, and soil moisture. Then the camera image is sent to the YOLO model, which detects aphids and slugs separately. The backend stores the pest counts, combines them with historical data and weather forecasts, predicts pest-pressure trends, and finally recommends whether to spray and how much product and water to use.

---

## 7. 对接时最容易出错的地方

| 问题 | 原因 | 解决 |
|---|---|---|
| Grafana 没数据 | `device_id` 用错 | 演示先用 `demo-trap-001` |
| telemetry 很多字段是 `null` | 旧硬件没有上传完整字段 | 硬件端补齐 `pressure_hpa`、`soil_moisture_pct` 等字段 |
| 前端只看到一个 count | 用了旧字段 `count` | 改用 `aphid_count`、`slug_count`、`total_count` |
| 喷药建议没触发 | aphid 数量太低或不在用药窗口 | 演示时用 `aphid_count=25`、`in_tepp_window=1` |
| 喷药量看起来过大 | 面积误填成 `2.0 ha` 这类大田面积 | 演示按 0.8 平方米填 `field_area_ha=0.00008` |
| 第一次打开很慢 | Azure Container Apps 冷启动 | 录制前先访问 `/health` 唤醒 |
| 图片上传失败 413 | 图片超过上传限制 | 压缩图片，默认限制约 50 MB |
| 英文演示页线上打不开 | 还没 push/deploy 新路由 | 先本地打开 HTML，部署后用 `/demo/dashboard/en` |

---

## 8. 不要在答辩前临时改这些

- 不要把 Grafana 临时改回 Log Analytics 业务表同步。
- 不要把 `aphid_count`、`slug_count`、`total_count` 字段名改掉。
- 不要把演示 `device_id` 临时换来换去。
- 不要把 Azure Storage key、GitHub secret、API key 写进文档或发给同学。
- 不要声称当前系统已经自动对 5 张图片取平均。当前稳定口径是一张图片一次识别。
- 不要在录制当天换模型权重，除非已经完整 smoke test。

---

## 9. 开会时可以直接复制给同学的话

给前端同学：

> 你不用直接读 Azure，全部调 API。图片识别用 `/predict`，趋势用 `/predict/trend`，预测用 `/forecast/auto`，喷药建议用 `/decision/weekly`。展示虫量时一定分开显示 `aphid_count`、`slug_count` 和 `total_count`。

给硬件同学：

> 你主要上传两类数据：传感器走 `/telemetry`，图片走 `/predict`。每一轮尽量带同一个 `round_id`，并补齐温度、湿度、气压、光照、土壤湿度、shots_planned。

给 Grafana 同学：

> Grafana 不直接查 Azure Table，也不走 Log Analytics。用 HTTP/JSON 数据源调用 `/grafana/telemetry`、`/grafana/aphidcounts`、`/grafana/decisionhistory`，数据都在返回 JSON 的 `items` 数组里。

---

## 10. 相关文档

- 完整 API：`docs/API_REFERENCE.md`
- 当前系统状态：`docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
- Grafana API 数据源：`docs/GRAFANA_API_DATASOURCE_QUICKSTART_CN.md`
- Grafana PAYG 说明：`docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
- 树莓派上传：`docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`
- 旧版团队交接：`docs/TEAM_COLLABORATION_HANDOFF_CN.md`
