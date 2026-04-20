"""Build real weekly retraining dataset by aggregating deployed API data.

Data sources:
1) /history for weekly aphid count proxy
2) /telemetry/latest for weekly mean temperature/humidity/pressure
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    """Parse CLI options for API fetch and weekly CSV output."""

    parser = argparse.ArgumentParser(
        description="Build real weekly observations CSV for Teppeki retraining from deployed API data.",
    )
    parser.add_argument(
        "--base-url",
        default="https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io",
        help="API base URL.",
    )
    parser.add_argument(
        "--out-csv",
        default="data/decision/weekly_observations.csv",
        help="Output CSV path used by auto_retrain_tepp.py.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=500,
        help="Limit for /history endpoint (max 500 in current API).",
    )
    parser.add_argument(
        "--device-ids",
        default="pi-001",
        help="Comma-separated device IDs for /telemetry/latest.",
    )
    parser.add_argument(
        "--telemetry-limit",
        type=int,
        default=500,
        help="Limit for /telemetry/latest endpoint (max 500 in current API).",
    )
    parser.add_argument(
        "--iot-api-key",
        default=os.getenv("IOT_API_KEY", ""),
        help="Optional API key for telemetry endpoints.",
    )
    parser.add_argument("--field-area-ha", type=float, default=1.0, help="Default field area value.")
    parser.add_argument("--default-t-mean", type=float, default=15.0, help="Fallback weekly mean temperature.")
    parser.add_argument("--default-rh-mean", type=float, default=70.0, help="Fallback weekly mean humidity.")
    parser.add_argument("--default-pressure-mean", type=float, default=1013.25, help="Fallback weekly mean pressure.")
    parser.add_argument("--timeout-sec", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail if no usable history records.",
    )
    return parser.parse_args()


def _normalize_base_url(base_url: str) -> str:
    """Remove trailing slash so endpoint joins are stable."""

    return base_url.rstrip("/")


def _week_start_monday(ts_utc: pd.Series) -> pd.Series:
    """Map UTC timestamps to their Monday week-start datetime."""

    # W-SUN means week ends Sunday, starts Monday.
    local = ts_utc.dt.tz_convert("UTC").dt.tz_localize(None)
    return local.dt.to_period("W-SUN").dt.start_time


def fetch_history(base_url: str, limit: int, timeout_sec: int) -> pd.DataFrame:
    """Fetch history records and normalize timestamp/count fields."""

    url = f"{base_url}/history"
    response = requests.get(url, params={"limit": limit}, timeout=timeout_sec)
    response.raise_for_status()
    payload = response.json()

    records = payload.get("records", [])
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        ts_raw = record.get("timestamp_utc") or record.get("history_last_modified_utc") or record.get("created_at")
        ts = pd.to_datetime(ts_raw, utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        count = pd.to_numeric(record.get("count", 0), errors="coerce")
        if pd.isna(count):
            count = 0.0
        rows.append(
            {
                "timestamp_utc": ts,
                "aphid_count": float(max(0.0, float(count))),
                "day": ts.date().isoformat(),
            }
        )
    return pd.DataFrame(rows)


def aggregate_history_weekly(history_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw history records into weekly aphid count/exposure summary."""

    if history_df.empty:
        return pd.DataFrame(columns=["week_start", "aphid_count", "exposure_days", "history_records"])

    df = history_df.copy()
    df["week_start"] = _week_start_monday(df["timestamp_utc"])
    weekly = (
        df.groupby("week_start", as_index=False)
        .agg(
            aphid_count=("aphid_count", "sum"),
            exposure_days=("day", "nunique"),
            history_records=("aphid_count", "size"),
        )
        .sort_values("week_start")
    )
    weekly["aphid_count"] = np.round(weekly["aphid_count"], 0).astype(int)
    weekly["exposure_days"] = weekly["exposure_days"].clip(lower=1, upper=14).astype(int)
    weekly["week_start"] = weekly["week_start"].dt.date.astype(str)
    return weekly


def fetch_telemetry(base_url: str, device_ids: list[str], limit: int, api_key: str, timeout_sec: int) -> pd.DataFrame:
    """Fetch latest telemetry rows for one or more devices."""

    headers = {"X-API-Key": api_key} if api_key else {}
    rows: list[dict[str, Any]] = []

    for device_id in device_ids:
        url = f"{base_url}/telemetry/latest"
        response = requests.get(
            url,
            params={"device_id": device_id, "limit": limit},
            headers=headers,
            timeout=timeout_sec,
        )
        # If telemetry is unavailable for a device, keep going for others.
        if response.status_code != 200:
            continue
        payload = response.json()
        items = payload.get("items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            ts = pd.to_datetime(item.get("ts"), utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            temp = pd.to_numeric(item.get("temperature"), errors="coerce")
            hum = pd.to_numeric(item.get("humidity"), errors="coerce")
            pressure = pd.to_numeric(item.get("pressure_hpa"), errors="coerce")
            rows.append(
                {
                    "timestamp_utc": ts,
                    "device_id": device_id,
                    "temperature": np.nan if pd.isna(temp) else float(temp),
                    "humidity": np.nan if pd.isna(hum) else float(hum),
                    "pressure_hpa": np.nan if pd.isna(pressure) else float(pressure),
                }
            )
    return pd.DataFrame(rows)


def aggregate_telemetry_weekly(telemetry_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw telemetry rows into weekly mean temperature/humidity/pressure."""

    if telemetry_df.empty:
        return pd.DataFrame(columns=["week_start", "T_mean", "RH_mean", "pressure_mean", "telemetry_records"])

    df = telemetry_df.copy()
    df["week_start"] = _week_start_monday(df["timestamp_utc"])
    weekly = (
        df.groupby("week_start", as_index=False)
        .agg(
            T_mean=("temperature", "mean"),
            RH_mean=("humidity", "mean"),
            pressure_mean=("pressure_hpa", "mean"),
            telemetry_records=("device_id", "size"),
        )
        .sort_values("week_start")
    )
    weekly["week_start"] = weekly["week_start"].dt.date.astype(str)
    return weekly


def build_weekly_observations(
    history_weekly: pd.DataFrame,
    telemetry_weekly: pd.DataFrame,
    field_area_ha: float,
    default_t_mean: float,
    default_rh_mean: float,
    default_pressure_mean: float,
) -> pd.DataFrame:
    """Merge weekly history + telemetry and fill mandatory retraining columns."""

    if history_weekly.empty:
        return pd.DataFrame(
            columns=[
                "week_start",
                "aphid_count",
                "exposure_days",
                "field_area_ha",
                "T_mean",
                "RH_mean",
                "pressure_mean",
                "in_tepp_window",
                "apps_so_far",
                "history_records",
                "telemetry_records",
            ]
        )

    merged = history_weekly.merge(telemetry_weekly, on="week_start", how="left")
    merged["T_mean"] = pd.to_numeric(merged["T_mean"], errors="coerce").fillna(default_t_mean)
    merged["RH_mean"] = pd.to_numeric(merged["RH_mean"], errors="coerce").fillna(default_rh_mean).clip(lower=0, upper=100)
    merged["pressure_mean"] = pd.to_numeric(merged.get("pressure_mean", np.nan), errors="coerce").fillna(
        default_pressure_mean
    )

    week_dt = pd.to_datetime(merged["week_start"], errors="coerce")
    doy = week_dt.dt.dayofyear.fillna(0).astype(int)
    merged["in_tepp_window"] = ((doy >= 135) & (doy <= 260)).astype(int)
    merged["apps_so_far"] = 0
    merged["field_area_ha"] = float(field_area_ha)
    merged["telemetry_records"] = pd.to_numeric(merged.get("telemetry_records", 0), errors="coerce").fillna(0).astype(int)

    ordered_cols = [
        "week_start",
        "aphid_count",
        "exposure_days",
        "field_area_ha",
        "T_mean",
        "RH_mean",
        "pressure_mean",
        "in_tepp_window",
        "apps_so_far",
        "history_records",
        "telemetry_records",
    ]
    return merged[ordered_cols].sort_values("week_start").reset_index(drop=True)


def main() -> None:
    """Run fetch + aggregate pipeline and write weekly_observations.csv."""

    args = parse_args()
    base_url = _normalize_base_url(args.base_url)
    device_ids = [d.strip() for d in args.device_ids.split(",") if d.strip()]
    if not device_ids:
        device_ids = ["pi-001"]

    history_raw = fetch_history(base_url=base_url, limit=args.history_limit, timeout_sec=args.timeout_sec)
    history_weekly = aggregate_history_weekly(history_raw)
    if history_weekly.empty and args.strict:
        raise RuntimeError("No usable /history records found; cannot build weekly observations in strict mode.")

    telemetry_raw = fetch_telemetry(
        base_url=base_url,
        device_ids=device_ids,
        limit=args.telemetry_limit,
        api_key=args.iot_api_key,
        timeout_sec=args.timeout_sec,
    )
    telemetry_weekly = aggregate_telemetry_weekly(telemetry_raw)

    weekly = build_weekly_observations(
        history_weekly=history_weekly,
        telemetry_weekly=telemetry_weekly,
        field_area_ha=args.field_area_ha,
        default_t_mean=args.default_t_mean,
        default_rh_mean=args.default_rh_mean,
        default_pressure_mean=args.default_pressure_mean,
    )

    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(out_path, index=False)

    print(f"[ok] history_rows_raw={len(history_raw)}")
    print(f"[ok] telemetry_rows_raw={len(telemetry_raw)}")
    print(f"[ok] weekly_rows={len(weekly)}")
    print(f"[ok] wrote: {out_path.resolve()}")


if __name__ == "__main__":
    main()

