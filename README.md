# PestinPeace - IoT Pest Monitoring

PestinPeace is an Azure-deployed IoT pest monitoring system. It combines Raspberry Pi image upload, YOLO aphid/slug detection, Azure Table + Blob storage, forecast/decision APIs, built-in dashboards, and Grafana-friendly API endpoints.

- Live API: `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`
- Main docs index: `docs/README.md`
- Defense assets: `defense_assets/README_CN.md`

## Architecture In 30 Seconds

```text
Raspberry Pi / Web upload
  -> POST /predict
  -> YOLO model detects aphid + slug
  -> Azure Blob stores images/history, Azure Table stores telemetry/count/decision data
  -> dashboards, Grafana, trend, forecast, and spray decision APIs read the same API layer
```

## Quick Checks

```bash
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/health"
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/ready"
curl "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/grafana/aphidcounts?device_id=demo-trap-001&limit=5"
```

Image prediction:

```bash
curl -X POST "https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict?device_id=demo-trap-001&conf=0.25" \
  -F "image=@test.jpg"
```

Important `/predict` fields:

- `aphid_count`: aphid detections used by trend/forecast/decision logic.
- `slug_count`: slug detections recorded for monitoring and dashboards.
- `total_count`: `aphid_count + slug_count`.
- `class_breakdown`: per-class count summary.
- `count`: backward-compatible alias for `aphid_count`.
- `count_mean`: backward-compatible single-image mean, currently equal to `aphid_count`.
- `detections`: raw boxes with `class_id`, `class_name`, confidence, and bbox.

## Current Business Logic

- Aphid is the main decision signal.
- Slug is an additional monitored class.
- Forecast and spray recommendation logic intentionally use `aphid_count`, not total pest count.
- Current capture mode is single image per request: `images_in_round = 1`, `aggregation_mode = single_image`.

## Where To Go Next

| Task | Read this |
|---|---|
| Current system status | `docs/CURRENT_SYSTEM_STATUS_AND_TESTING_CN.md` |
| Full API reference | `docs/API_REFERENCE.md` |
| Grafana setup | `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md` |
| Prediction and decision logic | `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md` |
| Model update checklist | `docs/MODEL_UPDATE.md` |
| Slug dataset notes | `ml/yolo/SLUG_DATASET_NOTES_CN.md` |
| Environment variables | `docs/ENV_VARS_REFERENCE.md` |
| Raspberry Pi upload | `docs/RASPBERRY_PI_TELEMETRY_UPLOAD_GUIDE_CN.md` |
| Local Pi decision client | `clients/raspberry_pi_decision/README.md` |
| Defense material | `defense_assets/README_CN.md` |

## Built-In Dashboard Routes

- `/predict/dashboard`
- `/telemetry/dashboard`
- `/history/dashboard`
- `/decision/dashboard`
- `/forecast/dashboard`

The root README is intentionally short. Detailed endpoint examples, deployment notes, and troubleshooting live under `docs/` to avoid stale duplicate instructions.
