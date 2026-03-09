#!/usr/bin/env python3
"""Local weekly aphid decision client for Raspberry Pi."""

from __future__ import annotations

import argparse
import json
import math
import pickle
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = BASE_DIR / "model" / "tepp_demo_scope_model.pkl"
DEFAULT_META_PATH = BASE_DIR / "model" / "tepp_demo_meta.json"
DEFAULT_STATE_PATH = BASE_DIR / "data" / "weekly_state.json"

DEFAULT_FEATURE_COLS = [
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
DEFAULT_TEACHER_Q50 = 0.5
DEFAULT_TEACHER_Q85 = 2.0
DEFAULT_TREATED_FRACTION = {0: 0.0, 1: 0.3, 2: 1.0}
DEFAULT_WATER_L_HA = {0: 0, 1: 350, 2: 500}
DEFAULT_RATE_KG_HA = 0.14


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the weekly aphid recommendation model locally on a Raspberry Pi."
    )
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON config file.")
    parser.add_argument("--state-file", type=Path, default=None, help="State JSON path.")
    parser.add_argument("--model-path", type=Path, default=None, help="Model .pkl path.")
    parser.add_argument("--meta-path", type=Path, default=None, help="Meta .json path.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_sample = subparsers.add_parser("add-sample", help="Append one observation into local weekly state.")
    add_sample.add_argument("--aphid-count", type=int, required=True, help="Observed aphid count for this sample.")
    add_sample.add_argument("--temperature", type=float, default=None, help="Temperature in Celsius.")
    add_sample.add_argument("--humidity", type=float, default=None, help="Relative humidity in percent.")
    add_sample.add_argument("--sensor", choices=["dht11", "dht22"], default=None, help="Read temperature/humidity from a DHT sensor.")
    add_sample.add_argument("--pin", type=int, default=None, help="GPIO pin used by the DHT sensor, such as 4.")
    add_sample.add_argument("--ts", default=None, help="Sample timestamp in ISO-8601 format.")

    recommend = subparsers.add_parser("recommend", help="Aggregate this week and run the local model.")
    recommend.add_argument("--field-area-ha", type=float, default=None, help="Field area in hectares.")
    recommend.add_argument("--week-start", default=None, help="Week start date in YYYY-MM-DD. Defaults to this week's Monday.")
    recommend.add_argument("--exposure-days", type=int, default=None, help="Exposure days passed into the model. Defaults to config or 7.")
    recommend.add_argument("--apps-so-far", type=int, default=None, help="Season application count override.")
    recommend.add_argument("--in-tepp-window", type=int, choices=[0, 1], default=None, help="Override application window flag.")
    recommend.add_argument("--ignore-compliance-gate", action="store_true", help="Skip the application window and max-application gate.")
    recommend.add_argument("--record-current", action="store_true", help="Record the current sample before running recommendation.")
    recommend.add_argument("--aphid-count", type=int, default=None, help="Aphid count for --record-current.")
    recommend.add_argument("--temperature", type=float, default=None, help="Temperature for --record-current.")
    recommend.add_argument("--humidity", type=float, default=None, help="Humidity for --record-current.")
    recommend.add_argument("--sensor", choices=["dht11", "dht22"], default=None, help="Read temperature/humidity for --record-current from a DHT sensor.")
    recommend.add_argument("--pin", type=int, default=None, help="GPIO pin for --record-current sensor reads.")
    recommend.add_argument("--ts", default=None, help="Timestamp for --record-current in ISO-8601 format.")

    mark_applied = subparsers.add_parser("mark-applied", help="Increment the season application count.")
    mark_applied.add_argument("--count", type=int, default=1, help="How many applications to add.")

    show_state = subparsers.add_parser("show-state", help="Print local state and weekly summaries.")
    show_state.add_argument("--week-start", default=None, help="Week start date in YYYY-MM-DD. Defaults to this week's Monday.")

    reset_season = subparsers.add_parser("reset-season", help="Reset the season application counter.")
    reset_season.add_argument("--clear-samples", action="store_true", help="Also remove stored observations.")

    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw if isinstance(raw, dict) else {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_path(cli_value: Path | None, config_value: str | None, default: Path, config_dir: Path | None) -> Path:
    if cli_value is not None:
        return cli_value.resolve()
    if config_value:
        candidate = Path(config_value)
        if not candidate.is_absolute() and config_dir is not None:
            candidate = (config_dir / candidate).resolve()
        return candidate
    return default.resolve()


def load_config(config_path: Path | None) -> tuple[dict[str, Any], Path | None]:
    if config_path is None:
        return {}, None
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return load_json(config_path.resolve()), config_path.resolve().parent


def default_state(today: date) -> dict[str, Any]:
    return {
        "season_year": today.year,
        "apps_so_far": 0,
        "samples": [],
    }


def load_state(path: Path, today: date) -> dict[str, Any]:
    if not path.exists():
        return default_state(today)
    payload = load_json(path)
    if "samples" not in payload or not isinstance(payload.get("samples"), list):
        payload["samples"] = []
    if not isinstance(payload.get("apps_so_far"), int):
        payload["apps_so_far"] = int(payload.get("apps_so_far", 0) or 0)
    if payload.get("season_year") != today.year:
        payload = default_state(today)
    return payload


def parse_iso_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_iso_date(raw: str | None, today: date) -> date:
    if not raw:
        return week_start_for(today)
    parsed = date.fromisoformat(raw)
    return parsed


def week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def normalize_scope_float_map(raw: Any, defaults: dict[int, float]) -> dict[int, float]:
    merged = dict(defaults)
    if not isinstance(raw, dict):
        return merged
    for key, value in raw.items():
        try:
            merged[int(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return merged


def normalize_scope_int_map(raw: Any, defaults: dict[int, int]) -> dict[int, int]:
    merged = dict(defaults)
    if not isinstance(raw, dict):
        return merged
    for key, value in raw.items():
        try:
            merged[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return merged


def read_dht_sensor(sensor_name: str, pin: int) -> tuple[float, float]:
    try:
        import adafruit_dht
        import board
    except ImportError as exc:
        raise RuntimeError(
            "DHT sensor dependencies are missing. Install adafruit-circuitpython-dht and board support first."
        ) from exc

    pin_attr = f"D{pin}"
    board_pin = getattr(board, pin_attr, None)
    if board_pin is None:
        raise RuntimeError(f"Unsupported pin for board module: {pin_attr}")

    sensor_cls = adafruit_dht.DHT22 if sensor_name.lower() == "dht22" else adafruit_dht.DHT11
    device = sensor_cls(board_pin, use_pulseio=False)
    last_error = None
    try:
        for _ in range(3):
            try:
                temperature = device.temperature
                humidity = device.humidity
                if temperature is not None and humidity is not None:
                    return float(temperature), float(humidity)
            except RuntimeError as exc:
                last_error = exc
        raise RuntimeError(f"Failed to read {sensor_name.upper()} sensor: {last_error}")
    finally:
        try:
            device.exit()
        except Exception:
            pass


def resolve_sensor_values(
    temperature: float | None,
    humidity: float | None,
    sensor_name: str | None,
    pin: int | None,
) -> tuple[float, float]:
    if temperature is not None and humidity is not None:
        return float(temperature), float(humidity)
    if sensor_name is None:
        raise ValueError("Temperature and humidity are required unless --sensor is provided.")
    if pin is None:
        raise ValueError("GPIO pin is required when using --sensor.")
    return read_dht_sensor(sensor_name, pin)


def build_sample(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    sensor_cfg = config.get("sensor", {}) if isinstance(config.get("sensor"), dict) else {}
    sensor_name = args.sensor or sensor_cfg.get("type")
    pin = args.pin if args.pin is not None else sensor_cfg.get("pin")
    temperature, humidity = resolve_sensor_values(args.temperature, args.humidity, sensor_name, pin)
    sample_ts = parse_iso_datetime(args.ts)
    return {
        "ts": sample_ts.isoformat(),
        "temperature": round(float(temperature), 3),
        "humidity": round(float(humidity), 3),
        "aphid_count": max(0, int(args.aphid_count)),
    }


def append_sample(state: dict[str, Any], sample: dict[str, Any]) -> None:
    state["samples"].append(sample)
    state["samples"] = sorted(state["samples"], key=lambda item: str(item.get("ts", "")))


def sample_date(sample: dict[str, Any]) -> date | None:
    raw = sample.get("ts")
    if not isinstance(raw, str):
        return None
    try:
        return parse_iso_datetime(raw).date()
    except ValueError:
        return None


def aggregate_week(samples: list[dict[str, Any]], week_start: date) -> dict[str, Any]:
    week_end = week_start + timedelta(days=7)
    selected: list[dict[str, Any]] = []
    for item in samples:
        day = sample_date(item)
        if day is None:
            continue
        if week_start <= day < week_end:
            selected.append(item)

    temperatures = [float(item["temperature"]) for item in selected if item.get("temperature") is not None]
    humidities = [float(item["humidity"]) for item in selected if item.get("humidity") is not None]
    unique_days = sorted({sample_date(item) for item in selected if sample_date(item) is not None})
    return {
        "week_start": week_start.isoformat(),
        "week_end": (week_end - timedelta(days=1)).isoformat(),
        "sample_count": len(selected),
        "observation_days": len(unique_days),
        "aphid_count": int(sum(max(0, int(item.get("aphid_count", 0) or 0)) for item in selected)),
        "t_mean": round(sum(temperatures) / len(temperatures), 3) if temperatures else None,
        "rh_mean": round(sum(humidities) / len(humidities), 3) if humidities else None,
    }


def vpd_kpa(t_c: float, rh_pct: float) -> float:
    es = 0.6108 * math.exp((17.27 * t_c) / (t_c + 237.3))
    ea = es * (rh_pct / 100.0)
    return max(es - ea, 0.0)


def resolve_doy(week_start: date) -> int:
    return week_start.timetuple().tm_yday


def resolve_tepp_window(week_start_doy: int, override: int | None) -> int:
    if override is not None:
        return 1 if int(override) == 1 else 0
    return 1 if 135 <= week_start_doy <= 260 else 0


def build_feature_map(
    *,
    aphid_count: int,
    exposure_days: int,
    week_start: date,
    prev_catch_rate: float | None,
    catch_trend: float | None,
    t_mean: float,
    rh_mean: float,
    vpd_mean: float | None,
    in_tepp_window: int | None,
    apps_so_far: int,
) -> dict[str, float]:
    catch_rate = float(aphid_count) / float(exposure_days)
    resolved_catch_trend = (
        float(catch_trend)
        if catch_trend is not None
        else (catch_rate - float(prev_catch_rate) if prev_catch_rate is not None else 0.0)
    )
    doy = resolve_doy(week_start)
    resolved_window = resolve_tepp_window(doy, in_tepp_window)
    vpd = float(vpd_mean) if vpd_mean is not None else vpd_kpa(float(t_mean), float(rh_mean))

    return {
        "catch_rate": catch_rate,
        "log_catch": math.log1p(catch_rate),
        "catch_trend": resolved_catch_trend,
        "T_mean": float(t_mean),
        "RH_mean": float(rh_mean),
        "VPD_mean": float(vpd),
        "doy_sin": math.sin(2.0 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2.0 * math.pi * doy / 365.25),
        "in_tepp_window": float(resolved_window),
        "apps_so_far": float(apps_so_far),
        "doy": float(doy),
    }


def scope_name(scope_class: int) -> str:
    if scope_class == 1:
        return "boundary_band"
    if scope_class == 2:
        return "full_field"
    return "no_spray"


def teacher_infer_scope(feature_map: dict[str, float], teacher_q50: float, teacher_q85: float) -> int:
    catch_rate = feature_map["catch_rate"]
    scope_class = 0
    if catch_rate >= teacher_q85:
        scope_class = 2
    elif catch_rate >= teacher_q50:
        scope_class = 1

    if scope_class == 1 and feature_map["catch_trend"] > 0.8 and feature_map["T_mean"] > 14:
        scope_class = 2
    return scope_class


def model_proba_map(model: Any, features: list[float]) -> dict[str, float] | None:
    if not hasattr(model, "predict_proba"):
        return None
    try:
        probabilities = model.predict_proba([features])[0]
    except Exception:
        return None

    classes_raw = getattr(model, "classes_", None)
    if classes_raw is None and hasattr(model, "named_steps"):
        clf = model.named_steps.get("clf")
        if clf is not None:
            classes_raw = getattr(clf, "classes_", None)
    if classes_raw is None:
        return None

    result: dict[str, float] = {}
    for index, class_id in enumerate(classes_raw):
        if index >= len(probabilities):
            continue
        result[str(int(class_id))] = float(probabilities[index])
    return result


def load_runtime(meta_path: Path, model_path: Path) -> dict[str, Any]:
    runtime = {
        "feature_cols": list(DEFAULT_FEATURE_COLS),
        "teacher_q50": DEFAULT_TEACHER_Q50,
        "teacher_q85": DEFAULT_TEACHER_Q85,
        "treated_fraction_by_scope": dict(DEFAULT_TREATED_FRACTION),
        "water_by_scope_l_ha": dict(DEFAULT_WATER_L_HA),
        "tepp_rate_kg_ha": DEFAULT_RATE_KG_HA,
        "meta_error": None,
        "model_error": None,
        "model": None,
    }

    if meta_path.exists():
        try:
            meta = load_json(meta_path)
            feature_cols = meta.get("feature_cols")
            if isinstance(feature_cols, list) and all(isinstance(item, str) for item in feature_cols):
                runtime["feature_cols"] = feature_cols
            teacher_quantiles = meta.get("teacher_quantiles", {})
            if isinstance(teacher_quantiles, dict):
                runtime["teacher_q50"] = float(teacher_quantiles.get("q50", runtime["teacher_q50"]))
                runtime["teacher_q85"] = float(teacher_quantiles.get("q85", runtime["teacher_q85"]))
            runtime["treated_fraction_by_scope"] = normalize_scope_float_map(
                meta.get("treated_fraction_by_scope"),
                runtime["treated_fraction_by_scope"],
            )
            runtime["water_by_scope_l_ha"] = normalize_scope_int_map(
                meta.get("water_by_scope_L_ha"),
                runtime["water_by_scope_l_ha"],
            )
            runtime["tepp_rate_kg_ha"] = float(meta.get("tepp_rate_kg_ha", runtime["tepp_rate_kg_ha"]))
        except Exception as exc:
            runtime["meta_error"] = str(exc)
    else:
        runtime["meta_error"] = f"Meta file not found: {meta_path}"

    if not model_path.exists():
        runtime["model_error"] = f"Model file not found: {model_path}"
        return runtime

    try:
        with model_path.open("rb") as f:
            runtime["model"] = pickle.load(f)
    except Exception as exc:
        runtime["model_error"] = str(exc)
    return runtime


def run_recommendation(
    runtime: dict[str, Any],
    *,
    aphid_count: int,
    field_area_ha: float,
    exposure_days: int,
    week_start: date,
    prev_catch_rate: float | None,
    catch_trend: float | None,
    t_mean: float,
    rh_mean: float,
    in_tepp_window: int | None,
    apps_so_far: int,
    respect_compliance_gate: bool,
) -> dict[str, Any]:
    feature_map = build_feature_map(
        aphid_count=aphid_count,
        exposure_days=exposure_days,
        week_start=week_start,
        prev_catch_rate=prev_catch_rate,
        catch_trend=catch_trend,
        t_mean=t_mean,
        rh_mean=rh_mean,
        vpd_mean=None,
        in_tepp_window=in_tepp_window,
        apps_so_far=apps_so_far,
    )
    feature_cols = runtime["feature_cols"]
    feature_values = [float(feature_map.get(column, 0.0)) for column in feature_cols]

    predicted_scope = None
    probabilities = None
    model_source = "teacher_rule_fallback"
    if runtime["model"] is not None:
        try:
            predicted_scope = int(runtime["model"].predict([feature_values])[0])
            probabilities = model_proba_map(runtime["model"], feature_values)
            model_source = "tepp_demo_scope_model"
        except Exception:
            predicted_scope = None

    if predicted_scope is None:
        predicted_scope = teacher_infer_scope(feature_map, runtime["teacher_q50"], runtime["teacher_q85"])
        model_source = "teacher_rule_fallback"
        probabilities = None

    scope_before_gate = int(predicted_scope)
    gate_applied = False
    gate_reason = None
    resolved_window = int(feature_map["in_tepp_window"])

    if respect_compliance_gate:
        if resolved_window != 1:
            predicted_scope = 0
            gate_applied = True
            gate_reason = "Outside Teppeki application window."
        elif apps_so_far >= 1:
            predicted_scope = 0
            gate_applied = True
            gate_reason = "Maximum application count reached (>= 1)."

    scope_class = int(max(0, min(2, predicted_scope)))
    treated_fraction = float(runtime["treated_fraction_by_scope"].get(scope_class, 0.0))
    water_l_ha = int(runtime["water_by_scope_l_ha"].get(scope_class, 0))
    product_kg = float(runtime["tepp_rate_kg_ha"] * field_area_ha * treated_fraction)
    spray_l = float(water_l_ha * field_area_ha * treated_fraction)

    model_error = runtime["model_error"]
    if runtime["meta_error"]:
        model_error = f"{runtime['meta_error']}; {model_error}" if model_error else runtime["meta_error"]

    return {
        "scope_class": scope_class,
        "scope_name": scope_name(scope_class),
        "treated_fraction": treated_fraction,
        "water_l_ha": water_l_ha,
        "product_kg": round(product_kg, 4),
        "spray_l": round(spray_l, 2),
        "inputs": {
            "aphid_count": aphid_count,
            "field_area_ha": field_area_ha,
            "exposure_days": exposure_days,
            "catch_rate": round(feature_map["catch_rate"], 4),
            "catch_trend": round(feature_map["catch_trend"], 4),
            "t_mean": round(feature_map["T_mean"], 3),
            "rh_mean": round(feature_map["RH_mean"], 3),
            "vpd_mean": round(feature_map["VPD_mean"], 4),
            "week_start": week_start.isoformat(),
            "week_start_doy": int(feature_map["doy"]),
            "in_tepp_window": resolved_window,
            "apps_so_far": apps_so_far,
        },
        "compliance": {
            "respect_compliance_gate": respect_compliance_gate,
            "scope_before_gate": scope_before_gate,
            "gate_applied": gate_applied,
            "gate_reason": gate_reason,
            "max_apps_allowed": 1,
        },
        "model": {
            "source": model_source,
            "loaded": runtime["model"] is not None,
            "feature_cols": feature_cols,
            "teacher_quantiles": {
                "q50": runtime["teacher_q50"],
                "q85": runtime["teacher_q85"],
            },
            "class_probabilities": probabilities,
            "error": model_error,
        },
        "label_constraints": {
            "tepp_rate_kg_ha": runtime["tepp_rate_kg_ha"],
            "water_range_l_ha": [200, 500],
        },
    }


def show_state_output(state: dict[str, Any], week_start: date) -> dict[str, Any]:
    current_week = aggregate_week(state["samples"], week_start)
    previous_week = aggregate_week(state["samples"], week_start - timedelta(days=7))
    return {
        "season_year": state["season_year"],
        "apps_so_far": state["apps_so_far"],
        "sample_count_total": len(state["samples"]),
        "current_week": current_week,
        "previous_week": previous_week,
    }


def main() -> None:
    args = parse_args()
    config, config_dir = load_config(args.config)
    today = datetime.now(timezone.utc).date()

    state_path = resolve_path(args.state_file, config.get("state_file"), DEFAULT_STATE_PATH, config_dir)
    model_path = resolve_path(args.model_path, config.get("model_path"), DEFAULT_MODEL_PATH, config_dir)
    meta_path = resolve_path(args.meta_path, config.get("meta_path"), DEFAULT_META_PATH, config_dir)

    state = load_state(state_path, today)

    if args.command == "add-sample":
        sample = build_sample(args, config)
        append_sample(state, sample)
        save_json(state_path, state)
        output = {
            "status": "ok",
            "saved_to": str(state_path),
            "sample": sample,
            "weekly_summary": aggregate_week(state["samples"], week_start_for(parse_iso_datetime(sample["ts"]).date())),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.command == "mark-applied":
        state["apps_so_far"] = max(0, int(state.get("apps_so_far", 0))) + max(0, int(args.count))
        save_json(state_path, state)
        print(json.dumps({"status": "ok", "apps_so_far": state["apps_so_far"], "saved_to": str(state_path)}, ensure_ascii=False, indent=2))
        return

    if args.command == "reset-season":
        if args.clear_samples:
            state = default_state(today)
        else:
            state["season_year"] = today.year
            state["apps_so_far"] = 0
        save_json(state_path, state)
        print(json.dumps({"status": "ok", "saved_to": str(state_path), "state": state}, ensure_ascii=False, indent=2))
        return

    if args.command == "show-state":
        week_start = parse_iso_date(args.week_start, today)
        print(json.dumps(show_state_output(state, week_start), ensure_ascii=False, indent=2))
        return

    if args.command != "recommend":
        raise RuntimeError(f"Unsupported command: {args.command}")

    if args.record_current:
        if args.aphid_count is None:
            raise ValueError("--aphid-count is required when using --record-current.")
        sample = build_sample(args, config)
        append_sample(state, sample)
        save_json(state_path, state)

    week_start = parse_iso_date(args.week_start, today)
    current_week = aggregate_week(state["samples"], week_start)
    previous_week = aggregate_week(state["samples"], week_start - timedelta(days=7))

    if current_week["sample_count"] == 0:
        raise ValueError("No samples found for the target week. Use add-sample first or recommend --record-current.")
    if current_week["t_mean"] is None or current_week["rh_mean"] is None:
        raise ValueError("Current week samples do not contain enough temperature/humidity data.")

    field_area_ha = args.field_area_ha
    if field_area_ha is None:
        field_area_ha = config.get("field_area_ha")
    if field_area_ha is None or float(field_area_ha) <= 0:
        raise ValueError("field_area_ha is required. Pass --field-area-ha or set it in config.")

    exposure_days = args.exposure_days
    if exposure_days is None:
        exposure_days = config.get("default_exposure_days", 7)
    exposure_days = int(exposure_days)
    if exposure_days < 1 or exposure_days > 14:
        raise ValueError("exposure_days must be between 1 and 14.")

    apps_so_far = args.apps_so_far if args.apps_so_far is not None else int(state.get("apps_so_far", 0))
    prev_catch_rate = None
    if previous_week["sample_count"] > 0:
        prev_catch_rate = float(previous_week["aphid_count"]) / float(exposure_days)

    runtime = load_runtime(meta_path, model_path)
    result = run_recommendation(
        runtime,
        aphid_count=int(current_week["aphid_count"]),
        field_area_ha=float(field_area_ha),
        exposure_days=exposure_days,
        week_start=week_start,
        prev_catch_rate=prev_catch_rate,
        catch_trend=None,
        t_mean=float(current_week["t_mean"]),
        rh_mean=float(current_week["rh_mean"]),
        in_tepp_window=args.in_tepp_window,
        apps_so_far=apps_so_far,
        respect_compliance_gate=not args.ignore_compliance_gate,
    )
    result["weekly_summary"] = {
        "current_week": current_week,
        "previous_week": previous_week,
        "state_file": str(state_path),
        "model_path": str(model_path),
        "meta_path": str(meta_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
