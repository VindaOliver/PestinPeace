from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local smoke test for apps/api/container FastAPI service.")
    parser.add_argument(
        "--app-dir",
        default="apps/api/container",
        help="Path to FastAPI app directory containing server.py and model/.",
    )
    parser.add_argument(
        "--sample-image",
        default="RickyPart/PestInPeace_rashberrypi/captures/photo_20260209_130739_1.jpg",
        help="Sample image file for /predict test.",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional output path for full JSON report.",
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return non-zero exit code when any check fails.",
    )
    return parser.parse_args()


def _load_server_module(app_dir: Path):
    server_path = app_dir / "server.py"
    if not server_path.exists():
        raise FileNotFoundError(f"Missing server.py: {server_path}")

    app_dir_str = str(app_dir)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)

    # Import as normal module; this path avoids pydantic forward-ref issues seen with exec_module.
    if "server" in sys.modules:
        del sys.modules["server"]
    module = importlib.import_module("server")
    return module


def _safe_json(response) -> dict[str, Any] | None:
    try:
        return response.json()
    except Exception:
        return None


def _resolve_dashboard_file(app_dir: Path, filename: str) -> Path:
    in_container_context = app_dir / filename
    if in_container_context.exists():
        return in_container_context

    # Fallback for restructured repo: apps/web/web_pages/*.html
    repo_root = app_dir.parent.parent.parent
    in_web_dir = repo_root / "apps" / "web" / "web_pages" / filename
    if in_web_dir.exists():
        return in_web_dir

    return in_container_context


def _expect_status(
    checks: list[CheckResult],
    name: str,
    actual: int,
    expected: int,
    detail: str = "",
) -> None:
    checks.append(
        CheckResult(
            name=name,
            passed=actual == expected,
            detail=f"expected={expected}, actual={actual}" + (f", {detail}" if detail else ""),
        )
    )


def main() -> int:
    args = parse_args()
    app_dir = Path(args.app_dir).resolve()
    model_dir = app_dir / "model"
    sample_image = Path(args.sample_image).resolve()

    # Force local model paths so import does not require /app bind mount.
    os.environ.setdefault("MODEL_PATH", str((model_dir / "best.pt").resolve()))
    os.environ.setdefault("TEPP_DEMO_MODEL_PATH", str((model_dir / "tepp_demo_scope_model.pkl").resolve()))
    os.environ.setdefault("TEPP_DEMO_META_PATH", str((model_dir / "tepp_demo_meta.json").resolve()))

    module = _load_server_module(app_dir)

    # Override dashboard file paths to local files for reliable local test.
    module.PREDICT_DASHBOARD_PATH = str(_resolve_dashboard_file(app_dir, "local_web_client.html").resolve())
    module.TELEMETRY_DASHBOARD_PATH = str(_resolve_dashboard_file(app_dir, "telemetry_dashboard.html").resolve())
    module.HISTORY_DASHBOARD_PATH = str(_resolve_dashboard_file(app_dir, "history_records.html").resolve())

    client = TestClient(module.app)
    checks: list[CheckResult] = []
    report: dict[str, Any] = {"checks": [], "responses": {}}

    # 1) Health
    r = client.get("/health")
    j = _safe_json(r)
    report["responses"]["health"] = {"status_code": r.status_code, "json": j}
    _expect_status(checks, "health_status", r.status_code, 200)
    if isinstance(j, dict):
        checks.append(CheckResult("health_ok_flag", j.get("status") == "ok", f"status={j.get('status')}"))
        checks.append(
            CheckResult(
                "tepp_model_loaded",
                bool(j.get("tepp_demo_model_enabled")),
                f"tepp_demo_model_enabled={j.get('tepp_demo_model_enabled')}",
            )
        )

    # 2) Dashboards
    for path in ["/predict/dashboard", "/telemetry/dashboard", "/history/dashboard"]:
        rr = client.get(path)
        report["responses"][path] = {"status_code": rr.status_code}
        _expect_status(checks, f"{path}_status", rr.status_code, 200)

    # 3) Decision weekly basic
    payload = {
        "aphid_count": 18,
        "field_area_ha": 2.0,
        "exposure_days": 7,
        "week_start": "2026-06-01",
        "t_mean": 16.4,
        "rh_mean": 72.0,
        "apps_so_far": 0,
        "respect_compliance_gate": True,
    }
    rr = client.post("/decision/weekly", json=payload)
    jj = _safe_json(rr)
    report["responses"]["decision_weekly"] = {"status_code": rr.status_code, "json": jj}
    _expect_status(checks, "decision_weekly_status", rr.status_code, 200)
    if isinstance(jj, dict):
        checks.append(CheckResult("decision_has_scope", "scope_class" in jj, f"scope_class={jj.get('scope_class')}"))
        checks.append(
            CheckResult(
                "decision_model_source",
                jj.get("model", {}).get("source") in {"tepp_demo_scope_model", "teacher_rule_fallback"},
                f"source={jj.get('model', {}).get('source')}",
            )
        )

    # 4) Decision compliance gate checks
    gate_cases = {
        "outside_window_gate_on": {
            "aphid_count": 50,
            "field_area_ha": 1.0,
            "week_start": "2026-01-10",
            "apps_so_far": 0,
            "respect_compliance_gate": True,
        },
        "max_apps_gate_on": {
            "aphid_count": 50,
            "field_area_ha": 1.0,
            "week_start": "2026-06-10",
            "apps_so_far": 1,
            "respect_compliance_gate": True,
        },
    }
    for name, body in gate_cases.items():
        rr = client.post("/decision/weekly", json=body)
        jj = _safe_json(rr) or {}
        report["responses"][name] = {"status_code": rr.status_code, "json": jj}
        _expect_status(checks, f"{name}_status", rr.status_code, 200)
        checks.append(
            CheckResult(
                f"{name}_scope_forced_zero",
                jj.get("scope_class") == 0,
                f"scope_class={jj.get('scope_class')}, gate_reason={jj.get('compliance', {}).get('gate_reason')}",
            )
        )

    # 5) Predict valid
    if sample_image.exists():
        with sample_image.open("rb") as f:
            rr = client.post("/predict", files={"image": (sample_image.name, f, "image/jpeg")})
        jj = _safe_json(rr)
        report["responses"]["predict_valid"] = {"status_code": rr.status_code, "json": jj}
        _expect_status(checks, "predict_valid_status", rr.status_code, 200)
        if isinstance(jj, dict):
            checks.append(CheckResult("predict_has_count", isinstance(jj.get("count"), int), f"count={jj.get('count')}"))
    else:
        checks.append(CheckResult("predict_valid_skipped", False, f"sample image not found: {sample_image}"))

    # 6) Predict invalid
    rr = client.post("/predict", files={"image": ("bad.txt", b"not an image", "text/plain")})
    jj = _safe_json(rr)
    report["responses"]["predict_invalid"] = {"status_code": rr.status_code, "json": jj}
    _expect_status(checks, "predict_invalid_status", rr.status_code, 400)

    # 7) History / telemetry behavior depends on Azure env config
    azure_blob_configured = bool(os.getenv("BLOB_CONNECTION_STRING", ""))
    azure_table_configured = bool(os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")) or azure_blob_configured

    rr = client.get("/history?limit=5")
    jj = _safe_json(rr)
    report["responses"]["history"] = {"status_code": rr.status_code, "json": jj}
    _expect_status(checks, "history_status", rr.status_code, 200 if azure_blob_configured else 503)

    rr = client.post(
        "/telemetry",
        json={"device_id": "pi-001", "temperature": 23.5, "humidity": 60.2, "light": 300},
    )
    jj = _safe_json(rr)
    report["responses"]["telemetry_post"] = {"status_code": rr.status_code, "json": jj}
    _expect_status(checks, "telemetry_post_status", rr.status_code, 200 if azure_table_configured else 503)

    rr = client.get("/telemetry/latest?device_id=pi-001&limit=5")
    jj = _safe_json(rr)
    report["responses"]["telemetry_latest"] = {"status_code": rr.status_code, "json": jj}
    _expect_status(checks, "telemetry_latest_status", rr.status_code, 200 if azure_table_configured else 503)

    passed = sum(1 for c in checks if c.passed)
    total = len(checks)
    report["checks"] = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks]
    report["summary"] = {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "strict": args.strict,
        "azure_blob_configured": azure_blob_configured,
        "azure_table_configured": azure_table_configured,
    }

    print(f"Smoke checks: {passed}/{total} passed")
    for c in checks:
        marker = "PASS" if c.passed else "FAIL"
        print(f"[{marker}] {c.name}: {c.detail}")

    if args.json_out:
        out_path = Path(args.json_out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report written: {out_path}")

    if args.strict and passed != total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
