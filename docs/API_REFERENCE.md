# API Reference

Base URL:

`https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

This document is the compact API reference for teammates. The current production system supports dual-class detection: `aphid` and `slug`.

## Health

```bash
curl "$BASE_URL/health"
curl "$BASE_URL/ready"
```

- `/health` reports service configuration and warnings.
- `/ready` is the deployment readiness check.

## Image Detection

`POST /predict`

Required:

- multipart field: `image`
- query parameter: `device_id`

Optional query parameters:

- `conf`, default `0.25`
- `iou`, default `0.45`
- `imgsz`, default `640`
- `max_det`, default `1000`

Example:

```bash
curl -X POST "$BASE_URL/predict?device_id=demo-trap-001&conf=0.25" \
  -F "image=@test.jpg"
```

Important response fields:

- `aphid_count`: aphid detections. This is the main input for trend, forecast, and spray decision logic.
- `slug_count`: slug detections. This is recorded for monitoring and Grafana.
- `total_count`: `aphid_count + slug_count`.
- `class_breakdown`: object such as `{"aphid": 12, "slug": 1}`.
- `class_breakdown_json`: Azure Table stores this as a string when persisted.
- `count`: kept for old clients, equal to `aphid_count`.
- `count_mean`: kept for old charts, currently equal to `aphid_count` because the system records one image per request.
- `images_in_round`: currently `1`.
- `aggregation_mode`: currently `single_image`.
- `detections`: raw detection boxes with `class_id`, `class_name`, `confidence`, and bbox fields.

Upload size is limited by `MAX_UPLOAD_BYTES`, currently `50000000` bytes by default.

## Telemetry Upload

`POST /telemetry`

Example:

```bash
curl -X POST "$BASE_URL/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"pi-001","temperature":24.6,"humidity":58.2,"light":301,"pressure_hpa":1012.4}'
```

Common fields:

- `device_id`
- `temperature`
- `humidity`
- `light`
- `pressure_hpa`
- `ts`

If `IOT_API_KEY` is configured, write requests must include `X-API-Key`.

## Telemetry Query

```bash
curl "$BASE_URL/telemetry/latest?device_id=pi-001&limit=10"
```

Use this for recent device readings. For Grafana and dashboard data, prefer the `/grafana/*` endpoints below.

If `IOT_API_KEY` is configured, `/telemetry/latest` also requires `X-API-Key`.

## Grafana / Table Query Endpoints

These endpoints expose Azure Table business data through the project API. Grafana can read them using an HTTP/JSON data source.

Current auth note:

- `/grafana/telemetry` requires `X-API-Key` when `IOT_API_KEY` is configured.
- `/grafana/aphidcounts` and `/grafana/decisionhistory` are currently public read endpoints for demo/Grafana convenience.
- If the project switches from public demo mode to private deployment, align all `/grafana/*` endpoints behind the same key gate.

```bash
curl "$BASE_URL/grafana/telemetry?device_id=demo-trap-001&limit=50"
curl "$BASE_URL/grafana/aphidcounts?device_id=demo-trap-001&limit=50"
curl "$BASE_URL/grafana/decisionhistory?device_id=demo-trap-001&limit=20"
```

Supported query parameters:

- `device_id`
- `from`
- `to`
- `limit`

Main `iottelemetry` fields:

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

Main `aphidcounts` fields:

- `ts_utc`
- `round_id`
- `request_id`
- `device_id`
- `count`
- `count_mean`
- `aphid_count`
- `slug_count`
- `total_count`
- `class_breakdown`
- `class_breakdown_json`
- `images_in_round`
- `aggregation_mode`

Main `decisionhistory` fields:

- `ts_utc`
- `decision_id`
- `scope_class`
- `scope_name`
- `should_spray`
- `spray_applied`
- `product_kg`
- `spray_l`
- `reason`

## Trend

```bash
curl "$BASE_URL/predict/trend?device_id=demo-trap-001&days=31"
```

The trend endpoint uses `aphid_count`. For old rows without `aphid_count`, the server falls back to `count`.

## Forecast

`POST /forecast/weekly`

Example:

```bash
curl -X POST "$BASE_URL/forecast/weekly" \
  -H "Content-Type: application/json" \
  -d '{"aphid_count":12,"exposure_days":7,"t_mean":16.0,"rh_mean":70.0,"pressure_mean":1012.0,"t_forecast":18.0,"rh_forecast":74.0,"pressure_forecast":1009.0}'
```

`GET /forecast/auto` can combine recent table data and weather forecast data automatically. If `IOT_API_KEY` is configured, it requires `X-API-Key`.

## Decision

`POST /decision/weekly`

Example:

```bash
curl -X POST "$BASE_URL/decision/weekly" \
  -H "Content-Type: application/json" \
  -d '{"aphid_count":18,"field_area_ha":2.0,"exposure_days":7,"t_mean":16.4,"rh_mean":72,"apps_so_far":0}'
```

Response includes:

- `scope_class`: `0=no_spray`, `1=boundary_band`, `2=full_field`
- `scope_name`
- `treated_fraction`
- `product_kg`
- `spray_l`
- model/fallback source information

## Decision History

```bash
curl "$BASE_URL/decision/history?device_id=demo-trap-001&limit=10"
```

The response includes recent decision records plus summary flags:

- `last_uploaded_record_is_spray`
- `last_uploaded_record_should_spray`

If `IOT_API_KEY` is configured, `/decision/history` requires `X-API-Key`.

## Prediction History

```bash
curl "$BASE_URL/history?limit=50"
```

This reads prediction history JSON from Blob storage.

## Built-In Dashboard Routes

- `/predict/dashboard`
- `/telemetry/dashboard`
- `/history/dashboard`
- `/decision/dashboard`
- `/forecast/dashboard`
