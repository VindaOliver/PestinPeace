from __future__ import annotations

import argparse
import json
import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train synthetic weekly Teppeki demo scope model.")
    parser.add_argument("--out-dir", default=".container_yolo26/model", help="Output directory for artifacts.")
    parser.add_argument("--start", default="2025-03-03", help="Start week (YYYY-MM-DD).")
    parser.add_argument("--n-weeks", type=int, default=32, help="Number of weekly samples.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def vpd_kpa(t_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    es = 0.6108 * np.exp((17.27 * t_c) / (t_c + 237.3))
    ea = es * (rh_pct / 100.0)
    return np.maximum(es - ea, 0.0)


def make_synthetic_weeks(rng: np.random.Generator, start: str = "2025-03-03", n_weeks: int = 32) -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=n_weeks, freq="W-MON")
    df = pd.DataFrame(
        {
            "week_start": dates.date.astype(str),
            "week_end": (dates + pd.Timedelta(days=6)).date.astype(str),
            "exposure_days": 7,
            "field_area_ha": 1.0,
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
    df["apps_so_far"] = 0

    risk = sigmoid(-2.0 + 0.22 * (df["T_mean"].to_numpy() - 10) + 0.9 * np.sin(2 * math.pi * (doy - 110) / 365.25))
    base_lambda_day = np.exp(-0.2 + 1.8 * risk)
    theta = 2.0
    gamma_mult = rng.gamma(shape=theta, scale=1 / theta, size=n_weeks)
    lambda_day = base_lambda_day * gamma_mult
    df["aphid_count"] = rng.poisson(lambda_day * 7)

    df["catch_rate"] = df["aphid_count"] / df["exposure_days"]
    df["log_catch"] = np.log1p(df["catch_rate"])
    df["catch_trend"] = df["catch_rate"].diff().fillna(0.0)
    df["doy_sin"] = np.sin(2 * math.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * math.pi * doy / 365.25)
    return df


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = make_synthetic_weeks(rng=rng, start=args.start, n_weeks=args.n_weeks)

    gate = (df["in_tepp_window"] == 1) & (df["apps_so_far"] < 1)
    q50 = float(df.loc[gate, "catch_rate"].quantile(0.50)) if gate.sum() >= 5 else 0.5
    q85 = float(df.loc[gate, "catch_rate"].quantile(0.85)) if gate.sum() >= 5 else 2.0

    scope = np.zeros(len(df), dtype=int)
    cr = df["catch_rate"].to_numpy()
    scope[(gate) & (cr >= q50) & (cr < q85)] = 1
    scope[(gate) & (cr >= q85)] = 2

    upgrade = (scope == 1) & (df["catch_trend"] > 0.8) & (df["T_mean"] > 14) & gate
    scope[upgrade] = 2

    noise_idx = rng.choice(len(df), size=max(1, int(0.05 * len(df))), replace=False)
    scope[noise_idx] = rng.integers(0, 3, size=len(noise_idx))

    df["scope_label"] = scope
    df["water_label"] = np.select([df["scope_label"].eq(1), df["scope_label"].eq(2)], [350, 500], default=0).astype(int)

    feature_cols = [
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
    x = df[feature_cols].values
    y = df["scope_label"].values

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    multi_class="multinomial",
                    max_iter=3000,
                    class_weight="balanced",
                    random_state=args.seed,
                ),
            ),
        ]
    )
    model.fit(x, y)

    csv_path = out_dir / "synthetic_weekly_trap.csv"
    pkl_path = out_dir / "tepp_demo_scope_model.pkl"
    meta_path = out_dir / "tepp_demo_meta.json"

    df.to_csv(csv_path, index=False)
    with pkl_path.open("wb") as f:
        pickle.dump(model, f)

    meta = {
        "feature_cols": feature_cols,
        "teacher_quantiles": {"q50": q50, "q85": q85},
        "treated_fraction_by_scope": {0: 0.0, 1: 0.3, 2: 1.0},
        "water_by_scope_L_ha": {0: 0, 1: 350, 2: 500},
        "tepp_rate_kg_ha": 0.14,
        "notes": "Synthetic demo only.",
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"[ok] rows={len(df)}")
    print(f"[ok] q50={q50:.6f}, q85={q85:.6f}")
    print(f"[ok] wrote: {csv_path}")
    print(f"[ok] wrote: {pkl_path}")
    print(f"[ok] wrote: {meta_path}")


if __name__ == "__main__":
    main()
