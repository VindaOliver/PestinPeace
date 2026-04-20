"""One-shot utility: fetch real weekly data from API, then retrain decision model."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse options for both fetch and retrain sub-steps."""

    parser = argparse.ArgumentParser(
        description="Fetch real weekly data from API and retrain Teppeki demo model in one command.",
    )
    parser.add_argument(
        "--base-url",
        default="https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io",
        help="API base URL.",
    )
    parser.add_argument(
        "--device-ids",
        default="pi-001",
        help="Comma-separated device IDs for telemetry fetch.",
    )
    parser.add_argument(
        "--out-weekly-csv",
        default="data/decision/weekly_observations.csv",
        help="Path to write weekly observations CSV.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=500,
        help="History fetch limit.",
    )
    parser.add_argument(
        "--telemetry-limit",
        type=int,
        default=500,
        help="Telemetry fetch limit per device.",
    )
    parser.add_argument(
        "--iot-api-key",
        default="",
        help="Optional API key for telemetry endpoints.",
    )
    parser.add_argument(
        "--field-area-ha",
        type=float,
        default=1.0,
        help="Default field area in hectares.",
    )
    parser.add_argument(
        "--default-t-mean",
        type=float,
        default=15.0,
        help="Fallback mean temperature when telemetry is missing.",
    )
    parser.add_argument(
        "--default-rh-mean",
        type=float,
        default=70.0,
        help="Fallback mean humidity when telemetry is missing.",
    )
    parser.add_argument(
        "--fetch-strict",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail on empty history result when fetching real data.",
    )
    parser.add_argument(
        "--retrain-out-dir",
        default="build/retrain/tepp",
        help="Retrain output directory (model/meta/report).",
    )
    parser.add_argument(
        "--label-source",
        choices=["teacher", "existing", "hybrid"],
        default="hybrid",
        help="Label source for retraining.",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=24,
        help="Minimum rows required by retraining.",
    )
    parser.add_argument(
        "--fallback-synthetic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow synthetic fallback if real data is missing/insufficient.",
    )
    parser.add_argument(
        "--synthetic-start",
        default="2025-03-03",
        help="Synthetic fallback start week.",
    )
    parser.add_argument(
        "--synthetic-weeks",
        type=int,
        default=52,
        help="Synthetic fallback weeks.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for retraining.",
    )
    parser.add_argument(
        "--rate-kg-ha",
        type=float,
        default=0.14,
        help="Fixed product rate for meta output.",
    )
    parser.add_argument(
        "--update-serving-dir",
        default="",
        help="Optional serving model dir to copy retrain artifacts into (manual release helper).",
    )
    return parser.parse_args()


def run_command(cmd: list[str]) -> None:
    """Execute a subprocess command and fail fast on non-zero exit code."""

    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    """Compose and run fetch + retrain commands in sequence."""

    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    fetch_script = script_dir / "build_weekly_observations_from_api.py"
    retrain_script = script_dir / "auto_retrain_tepp.py"

    if not fetch_script.exists():
        raise FileNotFoundError(f"Fetch script not found: {fetch_script}")
    if not retrain_script.exists():
        raise FileNotFoundError(f"Retrain script not found: {retrain_script}")

    out_weekly_csv = Path(args.out_weekly_csv)
    out_weekly_csv.parent.mkdir(parents=True, exist_ok=True)
    retrain_out_dir = Path(args.retrain_out_dir)
    retrain_out_dir.mkdir(parents=True, exist_ok=True)

    fetch_cmd = [
        sys.executable,
        str(fetch_script),
        "--base-url",
        args.base_url,
        "--out-csv",
        str(out_weekly_csv),
        "--history-limit",
        str(args.history_limit),
        "--device-ids",
        args.device_ids,
        "--telemetry-limit",
        str(args.telemetry_limit),
        "--field-area-ha",
        str(args.field_area_ha),
        "--default-t-mean",
        str(args.default_t_mean),
        "--default-rh-mean",
        str(args.default_rh_mean),
    ]
    if args.iot_api_key:
        fetch_cmd.extend(["--iot-api-key", args.iot_api_key])
    if args.fetch_strict:
        fetch_cmd.append("--strict")
    else:
        fetch_cmd.append("--no-strict")

    retrain_cmd = [
        sys.executable,
        str(retrain_script),
        "--weekly-csv",
        str(out_weekly_csv),
        "--out-dir",
        str(retrain_out_dir),
        "--label-source",
        args.label_source,
        "--min-rows",
        str(args.min_rows),
        "--synthetic-start",
        args.synthetic_start,
        "--synthetic-weeks",
        str(args.synthetic_weeks),
        "--seed",
        str(args.seed),
        "--rate-kg-ha",
        str(args.rate_kg_ha),
    ]
    if args.fallback_synthetic:
        retrain_cmd.append("--fallback-synthetic")
    else:
        retrain_cmd.append("--no-fallback-synthetic")
    if args.update_serving_dir:
        retrain_cmd.extend(["--update-serving-dir", args.update_serving_dir])

    run_command(fetch_cmd)
    run_command(retrain_cmd)

    print("[ok] one-shot fetch + retrain finished.")
    print(f"[ok] weekly csv: {out_weekly_csv.resolve()}")
    print(f"[ok] retrain out: {retrain_out_dir.resolve()}")


if __name__ == "__main__":
    main()

