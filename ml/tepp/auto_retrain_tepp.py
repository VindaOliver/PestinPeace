"""Automatic weekly decision-model retraining (training only, no deployment).

Pipeline summary:
1) Load weekly CSV if available and normalize schema
2) Build model features and labels (teacher/existing/hybrid)
3) Optionally append synthetic data if rows/classes are insufficient
4) Train + evaluate logistic model
5) Write model/meta/training dataset/report artifacts
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLS = [
    "log_catch",
    "catch_trend",
    "T_mean",
    "RH_mean",
    "VPD_mean",
    "doy_sin",
    "doy_cos",
    "in_tepp_window",
    "apps_so_far",
]


def parse_args() -> argparse.Namespace:
    """Parse retraining options for data source, labeling strategy, and output paths."""

    parser = argparse.ArgumentParser(
        description="Automatically retrain weekly demo spray-scope model. Training only, no deployment.",
    )
    parser.add_argument(
        "--weekly-csv",
        default="data/decision/weekly_observations.csv",
        help="Weekly data CSV path. If missing and --fallback-synthetic, synthetic data will be used.",
    )
    parser.add_argument(
        "--out-dir",
        default="build/retrain/tepp",
        help="Directory for retrained artifacts and report.",
    )
    parser.add_argument(
        "--label-source",
        choices=["teacher", "existing", "hybrid"],
        default="hybrid",
        help="Label source: teacher labels, existing scope_label, or hybrid(existing first).",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=24,
        help="Minimum rows before training; synthetic rows are appended when needed.",
    )
    parser.add_argument(
        "--fallback-synthetic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Append/use synthetic data if weekly CSV is missing or insufficient.",
    )
    parser.add_argument("--synthetic-start", default="2025-03-03", help="Synthetic start week.")
    parser.add_argument("--synthetic-weeks", type=int, default=52, help="Synthetic weeks generated for fallback.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--rate-kg-ha",
        type=float,
        default=0.14,
        help="Fixed product rate written to meta.",
    )
    parser.add_argument(
        "--update-serving-dir",
        default="",
        help="Optional model directory to copy artifacts into (manual release helper).",
    )
    return parser.parse_args()


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Standard logistic transform used by synthetic fallback generation."""

    return 1.0 / (1.0 + np.exp(-x))


def vpd_kpa(t_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """Compute VPD (kPa) from temperature and humidity arrays."""

    es = 0.6108 * np.exp((17.27 * t_c) / (t_c + 237.3))
    ea = es * (rh_pct / 100.0)
    return np.maximum(es - ea, 0.0)


def make_synthetic_weeks(rng: np.random.Generator, start: str = "2025-03-03", n_weeks: int = 52) -> pd.DataFrame:
    """Generate fallback synthetic weekly records when real data is missing/insufficient."""

    dates = pd.date_range(start=start, periods=n_weeks, freq="W-MON")
    df = pd.DataFrame(
        {
            "week_start": dates.date.astype(str),
            "exposure_days": 7,
            "field_area_ha": 1.0,
            "apps_so_far": 0,
        }
    )

    dt = pd.to_datetime(df["week_start"])
    doy = dt.dt.dayofyear.to_numpy()
    season = np.sin(2 * math.pi * (doy - 80) / 365.25)

    t_mean = 11 + 7 * season + rng.normal(0, 1.5, size=n_weeks)
    rh_mean = 78 - 8 * season + rng.normal(0, 5, size=n_weeks)
    rh_mean = np.clip(rh_mean, 40, 95)

    df["T_mean"] = np.round(t_mean, 2)
    df["RH_mean"] = np.round(rh_mean, 1)
    df["VPD_mean"] = np.round(vpd_kpa(df["T_mean"].to_numpy(), df["RH_mean"].to_numpy()), 3)
    df["in_tepp_window"] = ((doy >= 135) & (doy <= 260)).astype(int)

    risk = sigmoid(-2.0 + 0.22 * (df["T_mean"].to_numpy() - 10) + 0.9 * np.sin(2 * math.pi * (doy - 110) / 365.25))
    base_lambda_day = np.exp(-0.2 + 1.8 * risk)
    gamma_mult = rng.gamma(shape=2.0, scale=0.5, size=n_weeks)
    lambda_day = base_lambda_day * gamma_mult
    df["aphid_count"] = rng.poisson(lambda_day * df["exposure_days"].to_numpy())

    return df


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    """Find first matching column in a dataframe by alias list (case-insensitive)."""

    lower_map = {c.strip().lower(): c for c in df.columns}
    for alias in aliases:
        found = lower_map.get(alias.lower())
        if found:
            return found
    return None


def normalize_weekly_schema(raw: pd.DataFrame) -> pd.DataFrame:
    """Map flexible raw CSV schema into canonical column set expected by training."""

    out = pd.DataFrame()

    def copy_col(dst: str, aliases: list[str]) -> None:
        src = _pick_column(raw, aliases)
        if src:
            out[dst] = raw[src]

    copy_col("week_start", ["week_start", "date", "week", "week_date"])
    copy_col("aphid_count", ["aphid_count", "count", "trap_count", "aphids"])
    copy_col("exposure_days", ["exposure_days", "days"])
    copy_col("field_area_ha", ["field_area_ha", "area_ha"])
    copy_col("T_mean", ["T_mean", "t_mean", "temperature_mean"])
    copy_col("RH_mean", ["RH_mean", "rh_mean", "humidity_mean"])
    copy_col("VPD_mean", ["VPD_mean", "vpd_mean"])
    copy_col("in_tepp_window", ["in_tepp_window"])
    copy_col("apps_so_far", ["apps_so_far", "application_count"])
    copy_col("prev_catch_rate", ["prev_catch_rate"])
    copy_col("catch_trend", ["catch_trend"])
    copy_col("scope_label", ["scope_label"])

    if "aphid_count" not in out.columns:
        raise ValueError("Input weekly CSV must contain aphid_count (or alias like count/trap_count).")

    return out


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Clean/derive model features from normalized weekly records."""

    out = df.copy()
    n = len(out)

    if "week_start" not in out.columns:
        out["week_start"] = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=n, freq="W-MON").date.astype(str)
    out["week_start"] = pd.to_datetime(out["week_start"], errors="coerce")
    if out["week_start"].isna().any():
        fallback_dates = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=n, freq="W-MON")
        out.loc[out["week_start"].isna(), "week_start"] = fallback_dates[: out["week_start"].isna().sum()].to_pydatetime()

    out = out.sort_values("week_start").reset_index(drop=True)
    out["doy"] = out["week_start"].dt.dayofyear.astype(int)

    out["exposure_days"] = pd.to_numeric(out.get("exposure_days", 7), errors="coerce").fillna(7).clip(lower=1, upper=14)
    out["field_area_ha"] = pd.to_numeric(out.get("field_area_ha", 1.0), errors="coerce").fillna(1.0).clip(lower=0.01)
    out["aphid_count"] = pd.to_numeric(out["aphid_count"], errors="coerce").fillna(0).clip(lower=0)
    out["apps_so_far"] = pd.to_numeric(out.get("apps_so_far", 0), errors="coerce").fillna(0).clip(lower=0)
    out["T_mean"] = pd.to_numeric(out.get("T_mean", 15.0), errors="coerce").fillna(15.0)
    out["RH_mean"] = pd.to_numeric(out.get("RH_mean", 70.0), errors="coerce").fillna(70.0).clip(lower=0, upper=100)

    if "in_tepp_window" in out.columns:
        out["in_tepp_window"] = pd.to_numeric(out["in_tepp_window"], errors="coerce").fillna(-1)
        inferred = ((out["doy"] >= 135) & (out["doy"] <= 260)).astype(int)
        out["in_tepp_window"] = np.where(out["in_tepp_window"].isin([0, 1]), out["in_tepp_window"].astype(int), inferred)
    else:
        out["in_tepp_window"] = ((out["doy"] >= 135) & (out["doy"] <= 260)).astype(int)

    computed_vpd = vpd_kpa(out["T_mean"].to_numpy(), out["RH_mean"].to_numpy())
    out["VPD_mean"] = pd.to_numeric(out.get("VPD_mean", np.nan), errors="coerce")
    out["VPD_mean"] = out["VPD_mean"].fillna(pd.Series(computed_vpd)).clip(lower=0)

    out["catch_rate"] = out["aphid_count"] / out["exposure_days"]
    out["log_catch"] = np.log1p(out["catch_rate"])

    if "catch_trend" in out.columns and out["catch_trend"].notna().any():
        out["catch_trend"] = pd.to_numeric(out["catch_trend"], errors="coerce")
        if "prev_catch_rate" in out.columns:
            prev = pd.to_numeric(out["prev_catch_rate"], errors="coerce")
            fallback_trend = out["catch_rate"] - prev
            out["catch_trend"] = out["catch_trend"].fillna(fallback_trend)
        out["catch_trend"] = out["catch_trend"].fillna(out["catch_rate"].diff().fillna(0.0))
    elif "prev_catch_rate" in out.columns:
        prev = pd.to_numeric(out["prev_catch_rate"], errors="coerce")
        out["catch_trend"] = (out["catch_rate"] - prev).fillna(out["catch_rate"].diff().fillna(0.0))
    else:
        out["catch_trend"] = out["catch_rate"].diff().fillna(0.0)

    out["doy_sin"] = np.sin(2 * math.pi * out["doy"] / 365.25)
    out["doy_cos"] = np.cos(2 * math.pi * out["doy"] / 365.25)
    return out


def teacher_scope_label(df: pd.DataFrame) -> tuple[np.ndarray, float, float]:
    """Generate weak labels and quantile thresholds from trap rate under compliance gate."""

    gate = (df["in_tepp_window"] == 1) & (df["apps_so_far"] < 1)
    q50 = float(df.loc[gate, "catch_rate"].quantile(0.50)) if gate.sum() >= 5 else 0.5
    q85 = float(df.loc[gate, "catch_rate"].quantile(0.85)) if gate.sum() >= 5 else 2.0

    scope = np.zeros(len(df), dtype=int)
    cr = df["catch_rate"].to_numpy()
    scope[(gate) & (cr >= q50) & (cr < q85)] = 1
    scope[(gate) & (cr >= q85)] = 2

    upgrade = (scope == 1) & (df["catch_trend"] > 0.8) & (df["T_mean"] > 14) & gate
    scope[upgrade] = 2
    return scope, q50, q85


def choose_labels(df: pd.DataFrame, label_source: str) -> tuple[np.ndarray, float, float]:
    """Select training labels from teacher, existing labels, or hybrid strategy."""

    teacher, q50, q85 = teacher_scope_label(df)
    existing = None
    if "scope_label" in df.columns:
        existing = pd.to_numeric(df["scope_label"], errors="coerce")

    if label_source == "teacher":
        y = teacher
    elif label_source == "existing":
        if existing is None or existing.isna().all():
            raise ValueError("label_source=existing but scope_label is missing/empty.")
        y = existing.fillna(0).to_numpy(dtype=int)
    else:
        if existing is None:
            y = teacher
        else:
            hybrid = existing.copy()
            mask = hybrid.isna()
            hybrid.loc[mask] = teacher[mask.to_numpy()]
            y = hybrid.fillna(0).to_numpy(dtype=int)

    y = np.clip(y, 0, 2).astype(int)
    return y, q50, q85


def append_synthetic_if_needed(
    df: pd.DataFrame,
    y: np.ndarray,
    args: argparse.Namespace,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, np.ndarray, int]:
    """Append synthetic rows when dataset is too small or lacks class diversity."""

    rows_synthetic = 0
    class_count = len(np.unique(y))
    needs_more = len(df) < args.min_rows or class_count < 2
    if not needs_more:
        return df, y, rows_synthetic

    synth_raw = make_synthetic_weeks(rng=rng, start=args.synthetic_start, n_weeks=args.synthetic_weeks)
    synth = prepare_features(normalize_weekly_schema(synth_raw))
    synth_y, _, _ = choose_labels(synth, label_source="teacher")

    extra_rows = max(args.min_rows - len(df), 0)
    if extra_rows > 0:
        take = min(max(extra_rows, 12), len(synth))
        df = pd.concat([df, synth.head(take)], ignore_index=True)
        y = np.concatenate([y, synth_y[:take]])
        rows_synthetic += take

    if len(np.unique(y)) < 2:
        df = pd.concat([df, synth], ignore_index=True)
        y = np.concatenate([y, synth_y])
        rows_synthetic += len(synth)

    return df, y, rows_synthetic


def train_and_evaluate(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[Pipeline, dict[str, Any]]:
    """Train multinomial logistic model and return evaluation metrics."""

    model = Pipeline(
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

    y_series = pd.Series(y)
    can_split = len(y) >= 12 and y_series.value_counts().min() >= 2
    metrics: dict[str, Any] = {}

    if can_split:
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.25,
            random_state=seed,
            stratify=y,
        )
        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        metrics["evaluation_mode"] = "holdout"
        metrics["accuracy"] = float(accuracy_score(y_test, y_pred))
        metrics["macro_f1"] = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
        metrics["report"] = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        metrics["train_rows"] = int(len(y_train))
        metrics["test_rows"] = int(len(y_test))
    else:
        model.fit(x, y)
        y_pred = model.predict(x)
        metrics["evaluation_mode"] = "train_only"
        metrics["accuracy"] = float(accuracy_score(y, y_pred))
        metrics["macro_f1"] = float(f1_score(y, y_pred, average="macro", zero_division=0))
        metrics["report"] = classification_report(y, y_pred, output_dict=True, zero_division=0)
        metrics["train_rows"] = int(len(y))
        metrics["test_rows"] = 0

    return model, metrics


def main() -> None:
    """Execute retraining pipeline and write all artifacts/reports."""

    args = parse_args()
    rng = np.random.default_rng(args.seed)
    weekly_csv = Path(args.weekly_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_real = 0
    data_source = "weekly_csv"
    if weekly_csv.exists():
        raw = pd.read_csv(weekly_csv)
        df = prepare_features(normalize_weekly_schema(raw))
        rows_real = len(df)
    else:
        if not args.fallback_synthetic:
            raise FileNotFoundError(f"Weekly CSV not found and synthetic fallback disabled: {weekly_csv}")
        data_source = "synthetic_fallback"
        synth = make_synthetic_weeks(rng=rng, start=args.synthetic_start, n_weeks=args.synthetic_weeks)
        df = prepare_features(normalize_weekly_schema(synth))

    y, q50, q85 = choose_labels(df, label_source=args.label_source)

    rows_synthetic = 0
    if args.fallback_synthetic:
        df, y, rows_synthetic = append_synthetic_if_needed(df, y, args, rng)

    unique_classes = sorted(set(int(v) for v in np.unique(y)))
    if len(unique_classes) < 2:
        raise RuntimeError(
            "Training data has fewer than 2 classes after fallback. Add more weekly data with diverse conditions."
        )

    x = df[FEATURE_COLS].to_numpy(dtype=float)
    model, metrics = train_and_evaluate(x, y, seed=args.seed)

    training_df = df.copy()
    training_df["scope_label"] = y
    training_df["water_label"] = np.select(
        [training_df["scope_label"].eq(1), training_df["scope_label"].eq(2)],
        [350, 500],
        default=0,
    ).astype(int)

    model_path = out_dir / "tepp_demo_scope_model.pkl"
    meta_path = out_dir / "tepp_demo_meta.json"
    train_csv_path = out_dir / "weekly_training_dataset.csv"
    report_path = out_dir / "retrain_report.json"

    with model_path.open("wb") as f:
        pickle.dump(model, f)
    training_df.to_csv(train_csv_path, index=False)

    class_counts = {str(k): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()}
    meta = {
        "feature_cols": FEATURE_COLS,
        "teacher_quantiles": {"q50": q50, "q85": q85},
        "treated_fraction_by_scope": {0: 0.0, 1: 0.3, 2: 1.0},
        "water_by_scope_L_ha": {0: 0, 1: 350, 2: 500},
        "tepp_rate_kg_ha": float(args.rate_kg_ha),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_summary": {
            "source": data_source,
            "rows_total": int(len(training_df)),
            "rows_real": int(rows_real),
            "rows_synthetic": int(rows_synthetic if data_source != "synthetic_fallback" else len(training_df)),
            "class_counts": class_counts,
            "label_source": args.label_source,
        },
        "training_metrics": metrics,
        "notes": "Retrained by auto_retrain_tepp.py. Demo only; manual release required.",
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    report = {
        "args": vars(args),
        "artifacts": {
            "model_path": str(model_path.resolve()),
            "meta_path": str(meta_path.resolve()),
            "training_csv_path": str(train_csv_path.resolve()),
        },
        "data_summary": meta["data_summary"],
        "training_metrics": metrics,
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if args.update_serving_dir:
        serving_dir = Path(args.update_serving_dir)
        serving_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_path, serving_dir / "tepp_demo_scope_model.pkl")
        shutil.copy2(meta_path, serving_dir / "tepp_demo_meta.json")
        shutil.copy2(train_csv_path, serving_dir / "synthetic_weekly_trap.csv")
        print(f"[ok] copied artifacts to serving dir: {serving_dir.resolve()}")

    print(f"[ok] rows_total={len(training_df)}, classes={unique_classes}")
    print(f"[ok] metrics_mode={metrics['evaluation_mode']}, macro_f1={metrics['macro_f1']:.4f}")
    print(f"[ok] wrote: {model_path}")
    print(f"[ok] wrote: {meta_path}")
    print(f"[ok] wrote: {train_csv_path}")
    print(f"[ok] wrote: {report_path}")


if __name__ == "__main__":
    main()
