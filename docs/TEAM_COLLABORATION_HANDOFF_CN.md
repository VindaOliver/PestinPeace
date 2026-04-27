# 前端 / 硬件 + Grafana 同学对接说明

这份文档是给组内协作用的。目标不是解释所有代码，而是让两位同学知道：

- 他们各自负责什么
- 应该调用哪些接口
- 哪些字段最重要
- 遇到“没有数据”时先查哪里

当前线上 API：

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

演示数据推荐统一使用：

`device_id=demo-trap-001`

> 注意：`pi-001` 是真实/旧硬件上传数据，很多字段当时没有上传，所以会看到不少 `null`。如果要做答辩演示或 Grafana 面板，先用 `demo-trap-001`。

---

## 1. 总体分工

| 角色 | 负责内容 | 不建议负责 |
|---|---|---|
| 前端同学 | 页面展示、按钮交互、调用 API、把虫量/预测/决策结果画出来 | 不直接读 Azure Storage，不改模型和表结构 |
| 硬件 + Grafana 同学 | 传感器上传、拍照上传、Grafana 面板、确认数据是否进 API | 不直接改后端业务逻辑，不把旧 Log Analytics 方案重新接回来 |
| 后端/API 负责人 | 维护 API、Azure Table/Blob、YOLO 推理、forecast/decision 逻辑 | 不替前端决定页面样式，不替硬件决定传感器接线 |

最重要的一句话：

**所有业务数据都通过 API 读写，不要把 Azure Storage key 发给组员直接读表。**

---

## 2. 给前端同学的对接说明

### 2.1 前端应该接哪些接口

前端最常用的是这几个：

| 页面/功能 | 接口 | 用途 |
|---|---|---|
| 图片识别页面 | `POST /predict` | 上传图片，返回 aphid / slug 数量和框 |
| 历史记录页面 | `GET /history` | 看过去上传和识别结果 |
| 趋势图 | `GET /predict/trend` | 看最近虫量趋势 |
| 自动预测 | `GET /forecast/auto` | 自动结合最近表格数据和伦敦天气预测趋势 |
| 手动预测 | `POST /forecast/weekly` | 手动输入虫量和天气，预测未来趋势 |
| 喷药建议 | `POST /decision/weekly` | 根据虫量和环境数据算是否建议喷药 |
| 决策历史 | `GET /decision/history` | 看上一次是否喷药、历史喷药记录 |

### 2.2 前端最重要字段

虫量识别结果里请优先显示这些：

| 字段 | 含义 |
|---|---|
| `aphid_count` | 蚜虫数量，是预测和喷药决策主线 |
| `slug_count` | 蛞蝓数量，用于展示和监测 |
| `total_count` | 总虫量，等于 `aphid_count + slug_count` |
| `class_breakdown` | 按类别拆分的对象，例如 `{"aphid": 12, "slug": 1}` |
| `detections` | 每个检测框的位置、类别、置信度 |
| `count` | 旧兼容字段，语义等于 `aphid_count` |

前端不要再只显示旧字段 `count`，否则看起来像系统还是单类 aphid。

### 2.3 前端调用例子

图片识别：

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict?device_id=demo-trap-001&conf=0.25" \
  -F "image=@test.jpg"
```

趋势：

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict/trend?device_id=demo-trap-001&days=31"
```

喷药建议：

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/decision/weekly" \
  -H "Content-Type: application/json" \
  -d '{"aphid_count":18,"field_area_ha":0.00008,"exposure_days":7,"t_mean":16.4,"rh_mean":72,"apps_so_far":0}'
```

面积单位说明：`field_area_ha=0.00008` 表示 0.8 平方米。演示时不要再用 `2.0 ha`，否则喷药量会按 20,000 平方米计算。

喷头说明：当前后端按 Hunter MP1000 Rotator Nozzle 的演示规格换算，默认 `90° arc + 40 PSI + 0.21 GPM`，约 `13.25 ml/s`。喷药接口会返回 `nozzle.runtime_sec`，硬件演示时可以把它理解为喷头开启时间；0.8 平方米高风险全区喷施大约是 `40 ml / 3.0 s`，更适合录制。

自动预测：

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/forecast/auto?device_id=demo-trap-001&days=7"
```

### 2.4 前端验收标准

前端页面至少应该能做到：

- 图片上传后能显示 aphid 数量、slug 数量、总数量。
- 如果接口返回 `detections`，页面能画出检测框或至少展示检测列表。
- 趋势页面用 `aphid_count` 做主趋势，不用 `total_count` 触发喷药判断。
- 决策页面能展示 `scope_name`、`should_spray`、`product_kg` / `product_g`、`spray_l` / `spray_ml`、`nozzle.runtime_sec`。
- 页面不要硬编码旧 Azure URL，优先用当前线上 API base URL，或用 `location.origin`。

---

## 3. 给硬件同学的对接说明

### 3.1 硬件需要上传两类数据

硬件端主要做两件事：

1. 上传传感器数据到 `POST /telemetry`
2. 上传图片到 `POST /predict`

### 3.2 传感器上传接口

接口：

`POST /telemetry`

建议每一轮上传这些字段：

| 字段 | 含义 | 是否建议 |
|---|---|---|
| `device_id` | 设备 ID，例如 `pi-001` | 必须 |
| `round_id` | 一轮采集的 ID，用来把传感器和图片对齐 | 强烈建议 |
| `ts` | UTC 时间 | 建议 |
| `temperature_c` | 温度，摄氏度 | 必须 |
| `humidity_pct` | 湿度百分比 | 必须 |
| `pressure_hpa` | 气压 hPa | 强烈建议 |
| `lux_avg` | 光照平均值 | 建议 |
| `lux_valid` | 光照是否有效，0/1 | 建议 |
| `env_valid` | 环境传感器是否有效，0/1 | 建议 |
| `liquid_configured` | 液体传感器是否配置，0/1 | 建议 |
| `liquid_valid` | 液体传感器是否有效，0/1 | 建议 |
| `liquid_raw` | 液体传感器原始值，例如 -1/0/1 | 建议 |
| `liquid_has_liquid` | 是否检测到液体，0/1 | 建议 |
| `soil_valid` | 土壤传感器是否有效，0/1 | 建议 |
| `soil_raw` | 土壤原始值 | 建议 |
| `soil_moisture_pct` | 土壤湿度百分比 | 建议 |
| `fill_on` | 补光/填充灯是否开启，0/1 | 建议 |
| `shots_planned` | 本轮计划拍几张图 | 建议 |

完整例子：

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "pi-001",
    "round_id": "round_001",
    "temperature_c": 18.6,
    "humidity_pct": 71.2,
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

### 3.3 图片上传接口

接口：

`POST /predict?device_id=pi-001`

例子：

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict?device_id=pi-001&conf=0.25" \
  -F "image=@photo.jpg"
```

当前系统口径：

- 当前线上 API 是“一次请求上传一张图片”。
- 返回里的 `images_in_round` 目前是 `1`。
- 返回里的 `aggregation_mode` 目前是 `single_image`。
- 如果硬件实际想一轮拍 5 张，当前最稳做法是连续调用 `/predict` 5 次，并用同一个 `round_id` 方案在后续版本统一聚合。
- 答辩前不要口头说“系统已经自动对 5 张取平均”，除非后端明确新增 batch 聚合接口。

### 3.4 硬件验收标准

硬件端至少应该能做到：

- `POST /telemetry` 返回 `{"status":"ok"}`。
- `GET /grafana/telemetry?device_id=pi-001&limit=5` 能看到刚上传的数据。
- `POST /predict` 能返回 `aphid_count`、`slug_count`、`total_count`。
- 同一轮采集尽量使用同一个 `round_id`，方便之后把传感器和图片对应起来。
- 不要只上传 `temperature`、`humidity`、`light`，否则 Grafana 会看到很多 `null`。

---

## 4. 给 Grafana 同学的对接说明

### 4.1 Grafana 现在怎么取数

Grafana 现在不要直接查 Azure Table，也不要走旧的 Log Analytics 业务表。

推荐链路：

`Grafana -> HTTP/JSON Data Source -> Project API -> Azure Table`

### 4.2 Grafana 最常用接口

传感器数据：

```text
GET /grafana/telemetry?device_id=demo-trap-001&limit=50
```

虫量数据：

```text
GET /grafana/aphidcounts?device_id=demo-trap-001&limit=50
```

喷药决策历史：

```text
GET /grafana/decisionhistory?device_id=demo-trap-001&limit=20
```

带时间窗口：

```text
/grafana/telemetry?device_id=demo-trap-001&from=2026-03-21T00:00:00Z&to=2026-04-21T23:59:59Z&limit=500
```

### 4.3 Grafana 面板建议

建议做这些图：

| 面板 | 接口 | X 轴 | Y 轴 |
|---|---|---|---|
| 温度 | `/grafana/telemetry` | `ts_utc` | `temperature_c` |
| 湿度 | `/grafana/telemetry` | `ts_utc` | `humidity_pct` |
| 气压 | `/grafana/telemetry` | `ts_utc` | `pressure_hpa` |
| 土壤湿度 | `/grafana/telemetry` | `ts_utc` | `soil_moisture_pct` |
| aphid 数量 | `/grafana/aphidcounts` | `ts_utc` | `aphid_count` |
| slug 数量 | `/grafana/aphidcounts` | `ts_utc` | `slug_count` |
| 总虫量 | `/grafana/aphidcounts` | `ts_utc` | `total_count` |
| 喷药历史 | `/grafana/decisionhistory` | `ts_utc` | `should_spray` 或 `spray_applied` |

### 4.4 如果 Grafana 显示没有数据

按这个顺序查：

1. API base URL 是否是当前线上地址。
2. `device_id` 是否用的是 `demo-trap-001`。
3. 路径是否是 `/grafana/telemetry`、`/grafana/aphidcounts`、`/grafana/decisionhistory`。
4. 返回 JSON 里的数据在 `items` 数组里，不一定在根字段里。
5. 如果用 `pi-001`，很多传感器字段为 `null` 是正常的，因为旧硬件没有上传完整字段。
6. 虫量图不要只用旧字段 `count`，优先用 `aphid_count`、`slug_count`、`total_count`。

---

## 5. 你和两位同学开会时可以直接这样说

给前端同学：

> 你不用直接碰 Azure，也不用管表怎么存。你只管调 API。图片识别用 `/predict`，趋势用 `/predict/trend`，预测用 `/forecast/auto`，喷药建议用 `/decision/weekly`。虫量展示一定要分 `aphid_count`、`slug_count`、`total_count`，不要只用旧的 `count`。

给硬件 + Grafana 同学：

> 硬件上传传感器数据走 `/telemetry`，上传图片走 `/predict`。Grafana 不直接查 Azure Table，也不走 Log Analytics，统一用 `/grafana/telemetry`、`/grafana/aphidcounts`、`/grafana/decisionhistory`。演示先用 `demo-trap-001`，真实硬件 `pi-001` 要补齐气压、土壤、round_id、shots_planned 等字段，否则面板会有很多空值。

---

## 6. 相关文档

- 完整 API 字段：`docs/API_REFERENCE.md`
- Grafana 快速说明：`docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
- Grafana 中文快速说明：`docs/GRAFANA_API_DATASOURCE_QUICKSTART_CN.md`
- 树莓派上传说明：`docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md`
- 当前系统状态：`docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md`
