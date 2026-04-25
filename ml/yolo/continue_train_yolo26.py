"""Continue YOLO26 training from an existing checkpoint on new data.

Compared with fresh training, this script adds:
1) base-weight auto discovery
2) identical reporting artifacts as initial training
3) reproducible logging/validation behavior
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ultralytics
from ultralytics import YOLO, settings


def parse_args() -> argparse.Namespace:
    """Parse CLI options for continue-training workflow."""

    parser = argparse.ArgumentParser(
        description="Continue training from an existing YOLO weight on a new dataset."
    )
    parser.add_argument("--data", default="data.yaml", help="Path to NEW dataset yaml.")
    parser.add_argument(
        "--weights",
        default="",
        help="Base model weight path (best.pt/last.pt). If empty, auto-find latest best.pt in --search-root/runs.",
    )
    parser.add_argument(
        "--search-root",
        default=".",
        help="Directory used when auto-searching latest best.pt.",
    )
    parser.add_argument("--epochs", type=int, default=100, help="Number of continue-training epochs.")
    parser.add_argument("--imgsz", type=int, default=640, help="Training image size.")
    parser.add_argument("--batch", type=int, default=16, help="Batch size.")
    parser.add_argument("--device", default="0", help="CUDA device id, e.g. 0, or cpu.")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Dataloader workers. Default is 0 on Windows and 8 on non-Windows.",
    )
    parser.add_argument("--project", default="runs/train_continue", help="Output root directory.")
    parser.add_argument("--name", default="yolo26_aphid_continue", help="Experiment name.")
    parser.add_argument("--patience", type=int, default=50, help="Early stopping patience.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--save-period",
        type=int,
        default=1,
        help="Save checkpoint every N epochs. 1 means every epoch, -1 means only last/best.",
    )
    parser.add_argument(
        "--tensorboard",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable TensorBoard logging integration.",
    )
    parser.add_argument(
        "--cloud-loggers",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable cloud logger integrations (MLflow/Comet/ClearML/W&B/Neptune).",
    )
    parser.add_argument(
        "--val",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run final validation after training.",
    )
    return parser.parse_args()


def _safe_serialize(obj: Any) -> Any:
    """Convert nested objects to JSON-safe primitives."""

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)
    if hasattr(obj, "__dict__"):
        return _safe_serialize(vars(obj))
    return str(obj)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON payload with deterministic formatting."""

    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="ascii")


def _summarize_results_csv(results_csv: Path) -> dict[str, Any]:
    """Extract best/last epoch metrics from Ultralytics results.csv."""

    if not results_csv.exists():
        return {"error": f"File not found: {results_csv}"}

    with results_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return {"error": f"No rows in {results_csv}"}

    numeric_rows: list[dict[str, float]] = []
    for row in rows:
        parsed: dict[str, float] = {}
        for k, v in row.items():
            try:
                parsed[k] = float(v)
            except (TypeError, ValueError):
                continue
        numeric_rows.append(parsed)

    metric_candidates = [
        "metrics/mAP50-95(B)",
        "metrics/mAP50(B)",
        "metrics/precision(B)",
        "metrics/recall(B)",
    ]
    best_metric = next((m for m in metric_candidates if m in numeric_rows[-1]), None)

    if best_metric is None:
        best_idx = len(numeric_rows) - 1
    else:
        best_idx = max(range(len(numeric_rows)), key=lambda i: numeric_rows[i].get(best_metric, float("-inf")))

    return {
        "epochs_recorded": len(rows),
        "selected_best_metric": best_metric,
        "best_epoch_row_index": best_idx,
        "best_epoch_values": numeric_rows[best_idx],
        "last_epoch_values": numeric_rows[-1],
    }


def _build_artifact_manifest(run_dir: Path) -> dict[str, Any]:
    """List files generated in run_dir with relative path and file size."""

    if not run_dir.exists():
        return {"error": f"Run directory not found: {run_dir}"}

    files = []
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            files.append({"path": str(p.relative_to(run_dir)), "bytes": p.stat().st_size})

    return {"run_dir": str(run_dir), "file_count": len(files), "files": files}


def _write_presentation_report(run_dir: Path, csv_summary: dict[str, Any]) -> None:
    """Write a minimal markdown report for quick presentation usage."""

    lines = [
        "# Continue Training Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Run dir: {run_dir}",
        "",
        "## Core Files",
        "- `weights/best.pt`",
        "- `weights/last.pt`",
        "- `results.csv`",
        "- `results.png`",
        "- `confusion_matrix.png`",
        "",
        "## CSV Summary",
        f"- Epochs recorded: {csv_summary.get('epochs_recorded', 'N/A')}",
        f"- Selected best metric: {csv_summary.get('selected_best_metric', 'N/A')}",
        f"- Best epoch index: {csv_summary.get('best_epoch_row_index', 'N/A')}",
    ]
    (run_dir / "presentation_report.md").write_text("\n".join(lines), encoding="ascii")


def _find_latest_best_pt(search_root: Path) -> Path | None:
    """Find the most recently modified `runs/**/weights/best.pt` checkpoint."""

    candidates = list(search_root.glob("runs/**/weights/best.pt"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def main() -> None:
    """Run end-to-end continue training and export reports/artifacts."""

    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    data_path = Path(args.data)
    if not data_path.is_absolute():
        script_data_path = script_dir / data_path
        if script_data_path.exists():
            data_path = script_data_path
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_path.resolve()}")

    if args.weights:
        base_weights = Path(args.weights)
        if not base_weights.is_absolute():
            script_weights_path = script_dir / base_weights
            if script_weights_path.exists():
                base_weights = script_weights_path
    else:
        search_root = Path(args.search_root)
        if not search_root.is_absolute():
            script_search_root = script_dir / search_root
            if script_search_root.exists():
                search_root = script_search_root
        latest = _find_latest_best_pt(search_root)
        if latest is None:
            raise FileNotFoundError(
                "No best.pt found for continue training. Set --weights explicitly or check --search-root."
            )
        base_weights = latest

    if not base_weights.exists():
        raise FileNotFoundError(f"Base weights not found: {base_weights.resolve()}")

    workers = args.workers if args.workers is not None else (0 if platform.system() == "Windows" else 8)

    # Keep logger toggles explicit so runs are reproducible across machines.
    settings_payload = {"tensorboard": args.tensorboard}
    if not args.cloud_loggers:
        settings_payload.update(
            {
                "mlflow": False,
                "comet": False,
                "clearml": False,
                "wandb": False,
                "neptune": False,
            }
        )
    settings.update(settings_payload)

    model = YOLO(str(base_weights))
    train_results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=workers,
        project=args.project,
        name=args.name,
        patience=args.patience,
        save=True,
        plots=True,
        val=True,
        verbose=True,
        save_period=args.save_period,
        seed=args.seed,
        deterministic=True,
    )

    run_dir = Path(getattr(model.trainer, "save_dir", Path(args.project) / args.name))
    run_dir.mkdir(parents=True, exist_ok=True)

    train_context = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ultralytics_version": ultralytics.__version__,
        "base_weights": str(base_weights.resolve()),
        "data_yaml": str(data_path.resolve()),
        "args": vars(args),
        "resolved_workers": workers,
        "logger_settings": settings_payload,
        "train_results": _safe_serialize(train_results),
    }
    _write_json(run_dir / "train_context.json", train_context)

    csv_summary = _summarize_results_csv(run_dir / "results.csv")
    _write_json(run_dir / "results_summary.json", csv_summary)

    if args.val:
        val_metrics = model.val(data=str(data_path), device=args.device)
        _write_json(run_dir / "val_metrics.json", {"val_metrics": _safe_serialize(val_metrics)})

    manifest = _build_artifact_manifest(run_dir)
    _write_json(run_dir / "artifacts_manifest.json", manifest)
    _write_presentation_report(run_dir, csv_summary)


if __name__ == "__main__":
    main()
