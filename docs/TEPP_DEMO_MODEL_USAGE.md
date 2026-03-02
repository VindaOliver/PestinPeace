# Teppeki Demo 模型使用说明（`/decision/weekly`）

本文档说明周级喷施范围模型在本项目中的使用方式，以及现有数据是否满足输入要求。

## 1. 模型与接口

- 模型文件：
  - `apps/api/container/model/tepp_demo_scope_model.pkl`
  - `apps/api/container/model/tepp_demo_meta.json`
- 推理接口：`POST /decision/weekly`
- 输出重点：
  - `scope_class`（`0=不喷`，`1=边界带`，`2=全田`）
  - `water_l_ha`
  - `product_kg`
  - `spray_l`

## 2. 输入字段与项目数据可用性

### 2.1 必填字段

1. `aphid_count`
- 来源：`/predict` 的 `count`；或从 `/history` 按周聚合得到。
- 结论：可提供（需做周聚合）。

2. `field_area_ha`
- 来源：当前后端没有自动来源。
- 结论：需由配置、表单或数据库提供。

### 2.2 可选字段（建议提供）

1. `exposure_days`（默认 `7`）
- 可固定传 `7`。

2. `week_start`（`YYYY-MM-DD`）
- 客户端按周计算即可。

3. `t_mean` / `rh_mean`
- 来源：`/telemetry/latest` 里的 `temperature`、`humidity`，再做周均值。

4. `vpd_mean`
- 可不传，后端会用 `t_mean/rh_mean` 自动计算。

5. `prev_catch_rate` 或 `catch_trend`
- 建议传其中之一（可根据上周值计算）。

6. `in_tepp_window`
- 可不传，后端按 `week_start` 自动推断。

7. `apps_so_far`
- 当前项目没有施药次数持久化。
- 需手动输入或新增记录系统。

## 3. 当前项目结论

- 接口可调用：是（最小输入只需 `aphid_count + field_area_ha`）。
- 可形成稳定周级推荐：部分满足。
- 主要缺口：
  1. `field_area_ha` 缺系统化来源。
  2. `apps_so_far` 缺持久化记录。
  3. 缺自动“按周聚合”流程。

## 4. 推荐上线流程

1. 图像侧持续调用 `/predict`，数据沉淀到 `/history`。
2. 每周定时聚合：
  - `aphid_count`：周内虫数聚合值
  - `t_mean/rh_mean`：周内遥测均值
  - `prev_catch_rate`：上周值
  - `apps_so_far`：本季已施药次数
3. 调用 `/decision/weekly` 获取建议。
4. 人工确认后执行（不建议全自动施药闭环）。

## 5. 请求示例

```bash
curl -X POST "https://<your-app>/decision/weekly" \
  -H "Content-Type: application/json" \
  -d "{
    \"aphid_count\": 18,
    \"field_area_ha\": 2.0,
    \"exposure_days\": 7,
    \"week_start\": \"2026-03-02\",
    \"prev_catch_rate\": 1.4,
    \"t_mean\": 16.4,
    \"rh_mean\": 72.0,
    \"apps_so_far\": 0,
    \"respect_compliance_gate\": true
  }"
```

## 6. 响应解释

1. `scope_class`
- `0`：不喷
- `1`：边界带喷
- `2`：全田喷

2. 计算关系
- `product_kg = tepp_rate_kg_ha * field_area_ha * treated_fraction`
- `spray_l = water_l_ha * field_area_ha * treated_fraction`

3. 合规门控
- 若窗口外或 `apps_so_far >= 1`，且 `respect_compliance_gate=true`，会强制输出 `scope_class=0`。

## 7. 部署后检查

1. `GET /health`：
  - `tepp_demo_model_enabled = true`
  - `tepp_demo_model_error = null`
2. 镜像内文件存在：
  - `/app/model/tepp_demo_scope_model.pkl`
  - `/app/model/tepp_demo_meta.json`
3. 调用一次 `/decision/weekly`，确认 `model.source = tepp_demo_scope_model`（不是 fallback）。
