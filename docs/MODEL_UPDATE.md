# Model Update Checklist

This file explains which model artifacts are deployed with the Azure Container App and how to update them safely.

## Deployed Model Artifacts

The GitHub Actions workflow validates these files before building the Docker image:

| File | Purpose | If missing |
|---|---|---|
| `apps/api/container/model/best.pt` | YOLO aphid + slug image detector | `/predict` cannot load the model |
| `apps/api/container/model/tepp_demo_scope_model.pkl` | Weekly spray scope classifier | `/decision/weekly` falls back to rule logic or reports model load warnings |
| `apps/api/container/model/tepp_demo_meta.json` | Metadata for the TEPP decision model | Decision model explanation/feature mapping may be incomplete |
| `apps/api/container/model/aphid_forecast_model.pkl` | Weekly aphid trend forecast model | Forecast API falls back or reports model load warnings |
| `apps/api/container/model/aphid_forecast_meta.json` | Metadata for forecast model | Forecast explanation/feature mapping may be incomplete |

`apps/api/container/model/synthetic_weekly_trap.csv` is useful supporting data, but it is not part of the deployment validation checklist.

## YOLO Update Flow

1. Train and validate the model outside the container app folder.
2. Confirm the model names include:
   - `0: aphid`
   - `1: slug`
3. Copy the chosen checkpoint to:
   - `apps/api/container/model/best.pt`
4. Run local smoke tests if possible:

```bash
python scripts/tests/local_api_smoke.py
```

5. Push to GitHub. Normal pushes to `main` trigger deployment. Use `[skip ci]` only for docs/data changes that should not deploy.

## Decision And Forecast Model Update Flow

Update these files as pairs:

- `tepp_demo_scope_model.pkl` with `tepp_demo_meta.json`
- `aphid_forecast_model.pkl` with `aphid_forecast_meta.json`

Do not update only the `.pkl` file without the matching metadata unless you have verified the API still explains and maps features correctly.

## Compatibility Rule

For dual-class detection, keep this contract:

- `aphid_count` drives trend, forecast, and decision.
- `slug_count` is monitored/displayed.
- `total_count = aphid_count + slug_count`.
- `count = aphid_count` for old clients.

If this changes later, update `docs/API_REFERENCE.md`, dashboards, Grafana docs, Raspberry Pi docs, and smoke tests in the same PR.

