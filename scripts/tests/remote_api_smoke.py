from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test deployed API by HTTP calls.")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Deployed app base URL, e.g. https://<fqdn>",
    )
    parser.add_argument(
        "--sample-image",
        default="RickyPart/PestInPeace_rashberrypi/captures/photo_20260209_130739_1.jpg",
        help="Image used for /predict test.",
    )
    parser.add_argument(
        "--iot-api-key",
        default="",
        help="Optional API key for /telemetry endpoints.",
    )
    parser.add_argument(
        "--expect-history-status",
        default="200,503",
        help="Allowed HTTP status codes for /history, comma-separated.",
    )
    parser.add_argument(
        "--expect-telemetry-status",
        default="200,401,503",
        help="Allowed HTTP status codes for /telemetry and /telemetry/latest, comma-separated.",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path for full JSON report.",
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero if any check fails.",
    )
    return parser.parse_args()


def parse_allowed(raw: str) -> set[int]:
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out


def safe_json(resp: requests.Response) -> dict[str, Any] | None:
    try:
        return resp.json()
    except Exception:
        return None


def expect_status(checks: list[CheckResult], name: str, actual: int, allowed: set[int]) -> None:
    checks.append(
        CheckResult(
            name=name,
            passed=actual in allowed,
            detail=f"allowed={sorted(allowed)}, actual={actual}",
        )
    )


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    sample_image = Path(args.sample_image).resolve()
    history_allowed = parse_allowed(args.expect_history_status)
    telemetry_allowed = parse_allowed(args.expect_telemetry_status)

    headers = {}
    if args.iot_api_key:
        headers["X-API-Key"] = args.iot_api_key

    checks: list[CheckResult] = []
    report: dict[str, Any] = {"responses": {}, "checks": []}

    # 1) health
    r = requests.get(f"{base}/health", timeout=30)
    j = safe_json(r)
    report["responses"]["health"] = {"status_code": r.status_code, "json": j}
    expect_status(checks, "health_status", r.status_code, {200})
    if isinstance(j, dict):
        checks.append(CheckResult("health_ok_flag", j.get("status") == "ok", f"status={j.get('status')}"))

    # 2) dashboards
    for p in ["/predict/dashboard", "/telemetry/dashboard", "/history/dashboard", "/decision/dashboard"]:
        rr = requests.get(f"{base}{p}", timeout=30)
        report["responses"][p] = {"status_code": rr.status_code}
        expect_status(checks, f"{p}_status", rr.status_code, {200})

    # 3) decision weekly
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
    rr = requests.post(f"{base}/decision/weekly", json=payload, timeout=30)
    jj = safe_json(rr)
    report["responses"]["decision_weekly"] = {"status_code": rr.status_code, "json": jj}
    expect_status(checks, "decision_weekly_status", rr.status_code, {200})
    if isinstance(jj, dict):
        checks.append(CheckResult("decision_has_scope", "scope_class" in jj, f"scope_class={jj.get('scope_class')}"))

    # 4) predict valid/invalid
    if sample_image.exists():
        with sample_image.open("rb") as f:
            rr = requests.post(
                f"{base}/predict",
                files={"image": (sample_image.name, f, "image/jpeg")},
                timeout=60,
            )
        jj = safe_json(rr)
        report["responses"]["predict_valid"] = {"status_code": rr.status_code, "json": jj}
        expect_status(checks, "predict_valid_status", rr.status_code, {200})
    else:
        checks.append(CheckResult("predict_valid_status", False, f"missing sample image: {sample_image}"))

    rr = requests.post(
        f"{base}/predict",
        files={"image": ("bad.txt", b"not an image", "text/plain")},
        timeout=30,
    )
    report["responses"]["predict_invalid"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "predict_invalid_status", rr.status_code, {400})

    # 5) history
    rr = requests.get(f"{base}/history?limit=5", timeout=30)
    report["responses"]["history"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "history_status", rr.status_code, history_allowed)

    # 6) telemetry
    telemetry_payload = {"device_id": "pi-001", "temperature": 23.5, "humidity": 60.2, "light": 300}
    rr = requests.post(f"{base}/telemetry", json=telemetry_payload, headers=headers, timeout=30)
    report["responses"]["telemetry_post"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "telemetry_post_status", rr.status_code, telemetry_allowed)

    rr = requests.get(f"{base}/telemetry/latest?device_id=pi-001&limit=5", headers=headers, timeout=30)
    report["responses"]["telemetry_latest"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "telemetry_latest_status", rr.status_code, telemetry_allowed)

    passed = sum(1 for c in checks if c.passed)
    total = len(checks)
    report["checks"] = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks]
    report["summary"] = {"passed": passed, "failed": total - passed, "total": total, "strict": args.strict}

    print(f"Remote smoke checks: {passed}/{total} passed")
    for c in checks:
        marker = "PASS" if c.passed else "FAIL"
        print(f"[{marker}] {c.name}: {c.detail}")

    if args.json_out:
        out = Path(args.json_out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report written: {out}")

    if args.strict and passed != total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
