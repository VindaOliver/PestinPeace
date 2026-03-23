"""Train a weekly aphid trend forecast model with synthetic fallback support.

The model predicts:
1) trend_class in {-1, 0, 1} for down / stable / up
2) next week's catch_rate (regressed in log1p space)

Real weekly CSV rows are used when available, and synthetic weekly sequences are
appended when the observed dataset is too small or lacks class diversity.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLS = [
    "log_catch",
    "catch_trend",
    "T_mean",
    "RH_mean",
    "pressure_mean",
    "VPD_mean",
    "T_forecast",
    "RH_forecast",
    "pressure_forecast",
    "VPD_forecast",
    "temp_delta",
    "rh_delta",
    "pressure_delta",
    "doy_sin",
    "doy_cos",
    "in_tepp_window",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a weekly aphid trend + next-count forecast model.",
    )
    parser.add_argument(
        "--weekly-csv",
        default="build/weekly_observations_from_api.csv",
        help="Weekly observations CSV path. Shifted next-week weather is used as forecast proxy during training.",
    )
    parser.add_argument(
        "--out-dir",
        default="build/retrain/forecast",
        help="Directory for trained forecast artifacts and report.",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=36,
        help="Minimum forecast rows before training without synthetic augmentation.",
    )
    parser.add_argument(
        "--fallback-synthetic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Append/use synthetic weekly sequences when real data is missing or insufficient.",
    )
    parser.add_argument("--synthetic-start", default="2025-01-06", help="Synthetic start week.")
    parser.add_argument("--synthetic-weeks", type=int, default=104, help="Synthetic weeks to generate for fallback.")
    parser.add_argument("--stable-band", type=float, default=0.3, help="Absolute catch-rate delta treated as stable.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--update-serving-dir",
        default="",
        help="Optional model directory to copy artifacts into (manual release helper).",
    )
    return parser.parse_args()


def vpd_kpa(t_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    es = 0.6108 * np.exp((17.27 * t_c) / (t_c + 237.3))
    ea = es * (rh_pct / 100.0)
    return np.maximum(es - ea, 0.0)


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower_map = {c.strip().lower(): c for c in df.columns}
    for alias in aliases:
        found = lower_map.get(alias.lower())
        if found:
            return found
    return None


def normalize_weekly_schema(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()

    def copy_col(dst: str, aliases: list[str]) -> None:
        src = _pick_column(raw, aliases)
        if src:
            out[dst] = raw[src]

    copy_col("week_start", ["week_start", "date", "week", "week_date"])
    copy_col("aphid_count", ["aphid_count", "count", "trap_count", "aphids"])
    copy_col("exposure_days", ["exposure_days", "days"])
    copy_col("T_mean", ["T_mean", "t_mean", "temperature_mean"])
    copy_col("RH_mean", ["RH_mean", "rh_mean", "humidity_mean"])
    copy_col("pressure_mean", ["pressure_mean", "pressure_hpa", "pressure"])
    copy_col("history_records", ["history_records"])
    copy_col("telemetry_records", ["telemetry_records"])

    if "aphid_count" not in out.columns:
        raise ValueError("Input weekly CSV must contain aphid_count (or alias like count/trap_count).")

    return out


def make_synthetic_weekly_series(
    rng: np.random.Generator,
    start: str = "2025-01-06",
    n_weeks: int = 104,
) -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=n_weeks, freq="W-MON")
    df = pd.DataFrame(
        {
            "week_start": dates.date.astype(str),
            "exposure_days": 7,
            "history_records": 7,
            "telemetry_records": 14,
        }
    )

    doy = dates.dayofyear.to_numpy()
    season = np.sin(2 * math.pi * (doy - 90) / 365.25)

    t_mean = 12 + 8 * season + rng.normal(0, 1.4, size=n_weeks)
    rh_mean = 76 - 9 * season + rng.normal(0, 5, size=n_weeks)
    rh_mean = np.clip(rh_mean, 40, 96)
    pressure_mean = 1013.25 + 4 * np.cos(2 * math.pi * doy / 365.25) + rng.normal(0, 3.8, size=n_weeks)

    df["T_mean"] = np.round(t_mean, 2)
    df["RH_mean"] = np.round(rh_mean, 2)
    df["pressure_mean"] = np.round(pressure_mean, 2)

    counts = np.zeros(n_weeks, dtype=int)
    counts[0] = int(max(0, rng.poisson(2.5)))

    for idx in range(1, n_weeks):
        prev_rate = counts[idx - 1] / 7.0
        temp_signal = 0.10 * (df.loc[idx, "T_mean"] - 15.0)
        humidity_signal = 0.015 * (df.loc[idx, "RH_mean"] - 65.0)
        pressure_signal = 0.018 * (1013.25 - df.loc[idx, "pressure_mean"])
        season_signal = 0.55 * season[idx]
        memory_signal = 0.30 * math.log1p(prev_rate)
        shock = rng.normal(0, 0.28)

        next_rate = max(0.0, 0.45 + prev_rate + temp_signal + humidity_signal + pressure_signal + season_signal + shock)
        counts[idx] = int(rng.poisson(max(next_rate, 0.05) * 7.0))

    df["aphid_count"] = counts.astype(int)
    return df


def prepare_training_rows(df: pd.DataFrame, stable_band: float) -> pd.DataFrame:
    out = df.copy()
    n = len(out)
    if n == 0:
        return pd.DataFrame(columns=FEATURE_COLS + ["trend_class", "next_catch_rate_target", "next_count_target"])

    if "week_start" not in out.columns:
        out["week_start"] = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=n, freq="W-MON").date.astype(str)
    out["week_start"] = pd.to_datetime(out["week_start"], errors="coerce")
    if out["week_start"].isna().any():
        fallback_dates = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=n, freq="W-MON")
        out.loc[out["week_start"].isna(), "week_start"] = fallback_dates[: out["week_start"].isna().sum()].to_pydatetime()

    out = out.sort_values("week_start").reset_index(drop=True)

    def _col_or_default(name: str, default_value: float) -> pd.Series:
        if name in out.columns:
            return out[name]
        return pd.Series([default_value] * len(out), index=out.index)

    out["exposure_days"] = pd.to_numeric(_col_or_default("exposure_days", 7), errors="coerce").fillna(7).clip(lower=1, upper=14)
    out["aphid_count"] = pd.to_numeric(out["aphid_count"], errors="coerce").fillna(0).clip(lower=0)
    out["T_mean"] = pd.to_numeric(_col_or_default("T_mean", 15.0), errors="coerce").fillna(15.0)
    out["RH_mean"] = pd.to_numeric(_col_or_default("RH_mean", 70.0), errors="coerce").fillna(70.0).clip(lower=0, upper=100)
    out["pressure_mean"] = pd.to_numeric(_col_or_default("pressure_mean", 1013.25), errors="coerce").fillna(1013.25)

    out["catch_rate"] = out["aphid_count"] / out["exposure_days"]
    out["prev_catch_rate"] = out["catch_rate"].shift(1)
    out["catch_trend"] = (out["catch_rate"] - out["prev_catch_rate"]).fillna(0.0)
    out["log_catch"] = np.log1p(out["catch_rate"])
    out["VPD_mean"] = vpd_kpa(out["T_mean"].to_numpy(), out["RH_mean"].to_numpy())

    out["T_forecast"] = out["T_mean"].shift(-1)
    out["RH_forecast"] = out["RH_mean"].shift(-1)
    out["pressure_forecast"] = out["pressure_mean"].shift(-1)
    out["VPD_forecast"] = vpd_kpa(
        out["T_forecast"].fillna(out["T_mean"]).to_numpy(),
        out["RH_forecast"].fillna(out["RH_mean"]).to_numpy(),
    )

    out["temp_delta"] = out["T_forecast"] - out["T_mean"]
    out["rh_delta"] = out["RH_forecast"] - out["RH_mean"]
    out["pressure_delta"] = out["pressure_forecast"] - out["pressure_mean"]

    next_week_start = out["week_start"] + pd.to_timedelta(7, unit="D")
    out["doy"] = next_week_start.dt.dayofyear.astype(int)
    out["doy_sin"] = np.sin(2 * math.pi * out["doy"] / 365.25)
    out["doy_cos"] = np.cos(2 * math.pi * out["doy"] / 365.25)
    out["in_tepp_window"] = ((out["doy"] >= 135) & (out["doy"] <= 260)).astype(int)

    out["next_count_target"] = out["aphid_count"].shift(-1)
    out["next_exposure_days"] = out["exposure_days"].shift(-1)
    out["next_catch_rate_target"] = out["next_count_target"] / out["next_exposure_days"]
    out["delta_target"] = out["next_catch_rate_target"] - out["catch_rate"]

    out = out.dropna(
        subset=[
            "T_forecast",
            "RH_forecast",
            "pressure_forecast",
            "next_count_target",
            "next_catch_rate_target",
        ]
    ).reset_index(drop=True)

    out["trend_class"] = np.select(
        [out["delta_target"] > stable_band, out["delta_target"] < -stable_band],
        [1, -1],
        default=0,
    ).astype(int)

    out["next_count_target"] = out["next_count_target"].round(0).astype(int)
    out["next_catch_rate_target"] = out["next_catch_rate_target"].clip(lower=0)
    return out


def append_synthetic_if_needed(
    real_rows: pd.DataFrame,
    args: argparse.Namespace,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, int, str]:
    if not args.fallback_synthetic:
        return real_rows, 0, "real_only"

    rows_synthetic = 0
    class_count = len(set(int(v) for v in real_rows["trend_class"].unique())) if len(real_rows) else 0
    needs_more = len(real_rows) < args.min_rows or class_count < 2
    if not needs_more:
        return real_rows, 0, "real_only"

    synth_weekly = make_synthetic_weekly_series(rng=rng, start=args.synthetic_start, n_weeks=args.synthetic_weeks)
    synth_rows = prepare_training_rows(synth_weekly, stable_band=args.stable_band)

    if real_rows.empty:
        return synth_rows, len(synth_rows), "synthetic_only"

    extra_rows = max(args.min_rows - len(real_rows), 0)
    take = min(max(extra_rows, 18), len(synth_rows))
    merged = pd.concat([real_rows, synth_rows.head(take)], ignore_index=True)
    rows_synthetic += take

    if len(set(int(v) for v in merged["trend_class"].unique())) < 2:
        merged = pd.concat([merged, synth_rows], ignore_index=True)
        rows_synthetic += len(synth_rows)

    return merged.reset_index(drop=True), rows_synthetic, "real_plus_synthetic"


def build_classifier(seed: int) -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    multi_class="multinomial",
                    max_iter=3000,
                    class_weight="balanced",
                    random_state=seed,
                ),
            ),
        ]
    )


def build_regressor() -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("reg", Ridge(alpha=1.0)),
        ]
    )


def evaluate_and_fit(
    train_df: pd.DataFrame,
    seed: int,
) -> tuple[Pipeline, Pipeline, dict[str, Any], dict[str, Any]]:
    x = train_df[FEATURE_COLS].to_numpy(dtype=float)
    y_cls = train_df["trend_class"].to_numpy(dtype=int)
    y_reg = np.log1p(train_df["next_catch_rate_target"].to_numpy(dtype=float))

    classifier = build_classifier(seed=seed)
    regressor = build_regressor()

    y_series = pd.Series(y_cls)
    can_split = len(train_df) >= 18 and y_series.value_counts().min() >= 2

    if can_split:
        idx_train, idx_test = train_test_split(
            np.arange(len(train_df)),
            test_size=0.25,
            random_state=seed,
            stratify=y_cls,
        )
        x_train, x_test = x[idx_train], x[idx_test]
        y_cls_train, y_cls_test = y_cls[idx_train], y_cls[idx_test]
        y_reg_train, y_reg_test = y_reg[idx_train], y_reg[idx_test]
        classifier.fit(x_train, y_cls_train)
        regressor.fit(x_train, y_reg_train)

        pred_cls = classifier.predict(x_test)
        pred_reg_log = regressor.predict(x_test)
        pred_reg = np.maximum(np.expm1(pred_reg_log), 0.0)
        true_reg = np.maximum(np.expm1(y_reg_test), 0.0)

        cls_metrics = {
            "evaluation_mode": "holdout",
            "accuracy": float(accuracy_score(y_cls_test, pred_cls)),
            "macro_f1": float(f1_score(y_cls_test, pred_cls, average="macro", zero_division=0)),
            "report": classification_report(y_cls_test, pred_cls, output_dict=True, zero_division=0),
            "train_rows": int(len(idx_train)),
            "test_rows": int(len(idx_test)),
        }
        reg_metrics = {
            "evaluation_mode": "holdout",
            "mae_next_catch_rate": float(mean_absolute_error(true_reg, pred_reg)),
            "r2_next_catch_rate": float(r2_score(true_reg, pred_reg)),
            "train_rows": int(len(idx_train)),
            "test_rows": int(len(idx_test)),
        }
    else:
        classifier.fit(x, y_cls)
        regressor.fit(x, y_reg)

        pred_cls = classifier.predict(x)
        pred_reg_log = regressor.predict(x)
        pred_reg = np.maximum(np.expm1(pred_reg_log), 0.0)
        true_reg = np.maximum(np.expm1(y_reg), 0.0)

        cls_metrics = {
            "evaluation_mode": "train_only",
            "accuracy": float(accuracy_score(y_cls, pred_cls)),
            "macro_f1": float(f1_score(y_cls, pred_cls, average="macro", zero_division=0)),
            "report": classification_report(y_cls, pred_cls, output_dict=True, zero_division=0),
            "train_rows": int(len(train_df)),
            "test_rows": 0,
        }
        reg_metrics = {
            "evaluation_mode": "train_only",
            "mae_next_catch_rate": float(mean_absolute_error(true_reg, pred_reg)),
            "r2_next_catch_rate": float(r2_score(true_reg, pred_reg)),
            "train_rows": int(len(train_df)),
            "test_rows": 0,
        }

    return classifier, regressor, cls_metrics, reg_metrics


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    weekly_csv = Path(args.weekly_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_real = 0
    if weekly_csv.exists():
        raw = pd.read_csv(weekly_csv)
        real_rows = prepare_training_rows(normalize_weekly_schema(raw), stable_band=args.stable_band)
        rows_real = len(real_rows)
    else:
        real_rows = pd.DataFrame(columns=FEATURE_COLS + ["trend_class", "next_catch_rate_target", "next_count_target"])

    train_rows, rows_synthetic, data_source = append_synthetic_if_needed(real_rows=real_rows, args=args, rng=rng)
    if train_rows.empty:
        raise RuntimeError("No forecast rows available for training.")

    unique_classes = sorted(set(int(v) for v in train_rows["trend_class"].unique()))
    if len(unique_classes) < 2:
        raise RuntimeError("Training data has fewer than 2 trend classes even after fallback.")

    classifier, regressor, cls_metrics, reg_metrics = evaluate_and_fit(train_df=train_rows, seed=args.seed)

    model_payload = {
        "classifier": classifier,
        "regressor": regressor,
        "feature_cols": FEATURE_COLS,
        "stable_band": float(args.stable_band),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    model_path = out_dir / "aphid_forecast_model.pkl"
    meta_path = out_dir / "aphid_forecast_meta.json"
    training_csv_path = out_dir / "forecast_training_dataset.csv"
    report_path = out_dir / "forecast_retrain_report.json"

    with model_path.open("wb") as f:
        pickle.dump(model_payload, f)
    train_rows.to_csv(training_csv_path, index=False)

    class_counts = {str(k): int(v) for k, v in train_rows["trend_class"].value_counts().sort_index().items()}
    meta = {
        "feature_cols": FEATURE_COLS,
        "stable_band": float(args.stable_band),
        "trend_labels": {"-1": "down", "0": "stable", "1": "up"},
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_summary": {
            "source": data_source,
            "rows_total": int(len(train_rows)),
            "rows_real": int(rows_real),
            "rows_synthetic": int(rows_synthetic if data_source != "synthetic_only" else len(train_rows)),
            "class_counts": class_counts,
        },
        "classification_metrics": cls_metrics,
        "regression_metrics": reg_metrics,
        "notes": "Forecast model trained from weekly observations with synthetic fallback.",
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    report = {
        "args": vars(args),
        "artifacts": {
            "model_path": str(model_path.resolve()),
            "meta_path": str(meta_path.resolve()),
            "training_csv_path": str(training_csv_path.resolve()),
        },
        "data_summary": meta["data_summary"],
        "classification_metrics": cls_metrics,
        "regression_metrics": reg_metrics,
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if args.update_serving_dir:
        serving_dir = Path(args.update_serving_dir)
        serving_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_path, serving_dir / "aphid_forecast_model.pkl")
        shutil.copy2(meta_path, serving_dir / "aphid_forecast_meta.json")
        print(f"[ok] copied forecast artifacts to serving dir: {serving_dir.resolve()}")

    print(f"[ok] rows_total={len(train_rows)}, classes={unique_classes}, source={data_source}")
    print(f"[ok] classifier_mode={cls_metrics['evaluation_mode']}, macro_f1={cls_metrics['macro_f1']:.4f}")
    print(f"[ok] regressor_mode={reg_metrics['evaluation_mode']}, mae={reg_metrics['mae_next_catch_rate']:.4f}")
    print(f"[ok] wrote: {model_path}")
    print(f"[ok] wrote: {meta_path}")
    print(f"[ok] wrote: {training_csv_path}")
    print(f"[ok] wrote: {report_path}")


if __name__ == "__main__":
    main()
