"""Remote smoke test suite against deployed HTTP endpoints."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image


@dataclass
class CheckResult:
    """One endpoint/assertion check result."""

    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    """Parse remote smoke CLI options."""

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
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args()


def parse_allowed(raw: str) -> set[int]:
    """Parse comma-separated allowed status list into integer set."""

    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out


def safe_json(resp: requests.Response) -> dict[str, Any] | None:
    """Safely parse JSON body from requests response."""

    try:
        return resp.json()
    except Exception:
        return None


def ensure_sample_image(sample_image: Path) -> tuple[Path, bool]:
    """Return an existing sample image or create a tiny temporary fallback JPEG."""

    if sample_image.exists():
        return sample_image, False

    tmp = tempfile.NamedTemporaryFile(prefix="codex_remote_smoke_", suffix=".jpg", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    img = Image.new("RGB", (96, 96), color=(120, 190, 80))
    img.save(tmp_path, format="JPEG")
    return tmp_path, True


def expect_status(checks: list[CheckResult], name: str, actual: int, allowed: set[int]) -> None:
    """Record status-code assertion with allowed status set."""

    checks.append(
        CheckResult(
            name=name,
            passed=actual in allowed,
            detail=f"allowed={sorted(allowed)}, actual={actual}",
        )
    )


def main() -> int:
    """Run remote endpoint checks and return non-zero on failure (strict mode)."""

    args = parse_args()
    base = args.base_url.rstrip("/")
    sample_image = Path(args.sample_image).resolve()
    sample_image, generated_sample_image = ensure_sample_image(sample_image)
    history_allowed = parse_allowed(args.expect_history_status)
    telemetry_allowed = parse_allowed(args.expect_telemetry_status)
    timeout = max(5, int(args.timeout))

    headers = {}
    if args.iot_api_key:
        headers["X-API-Key"] = args.iot_api_key

    checks: list[CheckResult] = []
    report: dict[str, Any] = {"responses": {}, "checks": []}

    # 1) health
    r = requests.get(f"{base}/health", timeout=timeout)
    j = safe_json(r)
    report["responses"]["health"] = {"status_code": r.status_code, "json": j}
    expect_status(checks, "health_status", r.status_code, {200})
    if isinstance(j, dict):
        checks.append(CheckResult("health_ok_flag", j.get("status") == "ok", f"status={j.get('status')}"))

    # 2) dashboards
    for p in ["/predict/dashboard", "/telemetry/dashboard", "/history/dashboard", "/decision/dashboard", "/forecast/dashboard"]:
        rr = requests.get(f"{base}{p}", timeout=timeout)
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
    rr = requests.post(f"{base}/decision/weekly", json=payload, timeout=timeout)
    jj = safe_json(rr)
    report["responses"]["decision_weekly"] = {"status_code": rr.status_code, "json": jj}
    expect_status(checks, "decision_weekly_status", rr.status_code, {200})
    if isinstance(jj, dict):
        checks.append(CheckResult("decision_has_scope", "scope_class" in jj, f"scope_class={jj.get('scope_class')}"))

    # 4) predict valid/invalid
    with sample_image.open("rb") as f:
        rr = requests.post(
            f"{base}/predict?device_id=smoke-test-001",
            files={"image": (sample_image.name, f, "image/jpeg")},
            timeout=timeout,
        )
    jj = safe_json(rr)
    report["responses"]["predict_valid"] = {
        "status_code": rr.status_code,
        "json": jj,
        "generated_sample_image": generated_sample_image,
    }
    expect_status(checks, "predict_valid_status", rr.status_code, {200})
    if isinstance(jj, dict):
        checks.append(CheckResult("predict_has_count", isinstance(jj.get("count"), int), f"count={jj.get('count')}"))
        checks.append(
            CheckResult("predict_has_aphid_count", isinstance(jj.get("aphid_count"), int), f"aphid_count={jj.get('aphid_count')}")
        )
        checks.append(
            CheckResult("predict_has_slug_count", isinstance(jj.get("slug_count"), int), f"slug_count={jj.get('slug_count')}")
        )
        checks.append(
            CheckResult("predict_has_total_count", isinstance(jj.get("total_count"), int), f"total_count={jj.get('total_count')}")
        )
        checks.append(
            CheckResult(
                "predict_has_class_breakdown",
                isinstance(jj.get("class_breakdown"), dict),
                f"class_breakdown_type={type(jj.get('class_breakdown')).__name__}",
            )
        )
        checks.append(
            CheckResult(
                "predict_count_tracks_aphid_count",
                jj.get("count") == jj.get("aphid_count"),
                f"count={jj.get('count')}, aphid_count={jj.get('aphid_count')}",
            )
        )

    rr = requests.post(
        f"{base}/predict?device_id=smoke-test-001",
        files={"image": ("bad.txt", b"not an image", "text/plain")},
        timeout=timeout,
    )
    report["responses"]["predict_invalid"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "predict_invalid_status", rr.status_code, {400})

    # 5) history
    rr = requests.get(f"{base}/history?limit=5", timeout=timeout)
    report["responses"]["history"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "history_status", rr.status_code, history_allowed)

    # 6) telemetry
    telemetry_payload = {"device_id": "pi-001", "temperature": 23.5, "humidity": 60.2, "light": 300}
    rr = requests.post(f"{base}/telemetry", json=telemetry_payload, headers=headers, timeout=timeout)
    report["responses"]["telemetry_post"] = {"status_code": rr.status_code, "json": safe_json(rr)}
    expect_status(checks, "telemetry_post_status", rr.status_code, telemetry_allowed)

    rr = requests.get(f"{base}/telemetry/latest?device_id=pi-001&limit=5", headers=headers, timeout=timeout)
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
