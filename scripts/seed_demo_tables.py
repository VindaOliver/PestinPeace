"""Generate and seed clean demo data for the PAYG Azure Tables.

The script intentionally resets only one demo device partition. It is meant for
defense/demo data, not for production hardware records.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azure.data.tables import TableServiceClient


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "defense_assets" / "sample_data"
TELEMETRY_CSV = SAMPLE_DIR / "telemetry_mock_2026-03-21_to_2026-04-21.csv"
APHID_CSV = SAMPLE_DIR / "aphidcounts_mock_2026-03-21_to_2026-04-21.csv"
DECISION_CSV = SAMPLE_DIR / "decisionhistory_mock_2026-03-21_to_2026-04-21.csv"
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt.astimezone(timezone.utc)


def desc_row_key(ts: datetime, seq: int) -> str:
    ms = int(ts.timestamp() * 1000)
    inv = 9999999999999 - ms
    return f"{inv:013d}_{seq:04d}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def generate_aphid_rows(telemetry_rows: list[dict[str, str]], device_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    first_day = parse_utc(telemetry_rows[0]["ts_utc"]).date()
    for idx, source in enumerate(telemetry_rows, start=1):
        ts = parse_utc(source["ts_utc"])
        day_index = (ts.date() - first_day).days
        sample_in_day = 0 if ts.hour < 15 else 1

        # Smooth spring rise with small deterministic day/time variation.
        base = 2 + (day_index * 0.42)
        wave = [0, 1, 0, -1, 0, 1, 0][day_index % 7]
        aphid_count = max(1, min(16, int(round(base + wave + sample_in_day))))

        # Slug is intentionally rarer: roughly low-frequency detections for demo realism.
        slug_count = 0
        if day_index >= 10 and (day_index + sample_in_day) % 6 == 0:
            slug_count = 1
        if day_index >= 22 and sample_in_day == 1 and day_index % 4 == 0:
            slug_count = 2

        breakdown = {"aphid": aphid_count}
        if slug_count > 0:
            breakdown["slug"] = slug_count
        total_count = aphid_count + slug_count
        stamp = ts.strftime("%Y%m%d_%H%M%S")

        out.append(
            {
                "ts_utc": source["ts_utc"],
                "round_id": source["round_id"],
                "request_id": f"pred_{stamp}_{idx:03d}",
                "device_id": device_id,
                "filename": f"{device_id}_{stamp}.jpg",
                "count": aphid_count,
                "count_mean": f"{float(aphid_count):.4f}",
                "aphid_count": aphid_count,
                "slug_count": slug_count,
                "total_count": total_count,
                "class_breakdown_json": json.dumps(breakdown, sort_keys=True),
                "images_in_round": 1,
                "aggregation_mode": "single_image",
                "image_blob_name": f"sample-images/{device_id}/{stamp}.jpg",
                "history_blob_name": f"sample-history/{device_id}/{stamp}.json",
            }
        )
    return out


def telemetry_entity(row: dict[str, str], device_id: str, seq: int) -> dict[str, Any]:
    ts = parse_utc(row["ts_utc"])
    return {
        "PartitionKey": device_id,
        "RowKey": desc_row_key(ts, seq),
        "device_id": device_id,
        "ts": row["ts_utc"],
        "ts_utc": row["ts_utc"],
        "round_id": row["round_id"],
        "temperature": float(row["temperature_c"]),
        "temperature_c": float(row["temperature_c"]),
        "humidity": float(row["humidity_pct"]),
        "humidity_pct": float(row["humidity_pct"]),
        "pressure_hpa": float(row["pressure_hpa"]),
        "light": float(row["lux_avg"]),
        "lux_avg": float(row["lux_avg"]),
        "lux_valid": int(row["lux_valid"]),
        "env_valid": int(row["env_valid"]),
        "soil_valid": int(row["soil_valid"]),
        "soil_raw": int(row["soil_raw"]),
        "soil_moisture_pct": float(row["soil_moisture_pct"]),
        "fill_on": int(row["fill_on"]),
        "shots_planned": int(row["shots_planned"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def aphid_entity(row: dict[str, Any], seq: int) -> dict[str, Any]:
    ts = parse_utc(str(row["ts_utc"]))
    return {
        "PartitionKey": row["device_id"],
        "RowKey": desc_row_key(ts, seq),
        "device_id": row["device_id"],
        "source_device_id": row["device_id"],
        "request_id": row["request_id"],
        "round_id": row["round_id"],
        "ts": row["ts_utc"],
        "ts_utc": row["ts_utc"],
        "filename": row["filename"],
        "count": int(row["count"]),
        "count_mean": float(row["count_mean"]),
        "aphid_count": int(row["aphid_count"]),
        "slug_count": int(row["slug_count"]),
        "total_count": int(row["total_count"]),
        "class_breakdown_json": row["class_breakdown_json"],
        "images_in_round": int(row["images_in_round"]),
        "aggregation_mode": row["aggregation_mode"],
        "image_blob_name": row["image_blob_name"],
        "history_blob_name": row["history_blob_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def decision_entity(row: dict[str, str], device_id: str, seq: int) -> dict[str, Any]:
    ts = parse_utc(row["ts_utc"])
    return {
        "PartitionKey": device_id,
        "RowKey": desc_row_key(ts, seq),
        "device_id": device_id,
        "decision_id": row["decision_id"],
        "round_id": row["round_id"],
        "ts": row["ts_utc"],
        "ts_utc": row["ts_utc"],
        "scope_class": int(row["scope_class"]),
        "scope_name": row["scope_name"],
        "should_spray": bool(int(row["should_spray"])),
        "spray_applied": bool(int(row["spray_applied"])),
        "product_kg": float(row["product_kg"]),
        "spray_l": float(row["spray_l"]),
        "source": row["source"],
        "reason": row["reason"],
        "notes": row["notes"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def delete_partition(table_client: Any, partition_key: str) -> int:
    if not DEVICE_ID_RE.fullmatch(partition_key):
        raise ValueError("device_id may only contain letters, numbers, dot, underscore, or hyphen.")
    rows = list(table_client.query_entities(f"PartitionKey eq '{partition_key}'"))
    for row in rows:
        table_client.delete_entity(row["PartitionKey"], row["RowKey"])
    return len(rows)


def upsert_many(table_client: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        table_client.upsert_entity(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed clean demo data into Azure Tables.")
    parser.add_argument("--device-id", default="demo-trap-001")
    parser.add_argument("--connection-string", default=os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""))
    parser.add_argument("--telemetry-table", default="iottelemetry")
    parser.add_argument("--aphid-table", default="aphidcounts")
    parser.add_argument("--decision-table", default="decisionhistory")
    parser.add_argument("--reset", action="store_true", help="Delete existing rows for this device partition first.")
    parser.add_argument("--write-azure", action="store_true", help="Write generated rows to Azure Table Storage.")
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="Allow writing to a non-demo device id. Keep this off for defense/demo resets.",
    )
    args = parser.parse_args()
    if not DEVICE_ID_RE.fullmatch(args.device_id):
        raise SystemExit("Invalid device id. Use only letters, numbers, dot, underscore, or hyphen.")
    if args.write_azure and not args.device_id.startswith("demo-") and not args.allow_prod:
        raise SystemExit(
            "Refusing to write non-demo device data. Use a device id starting with 'demo-' "
            "or pass --allow-prod if you really intend to modify production-like rows."
        )

    telemetry_rows = read_csv(TELEMETRY_CSV)
    aphid_rows = generate_aphid_rows(telemetry_rows, args.device_id)
    decision_rows = read_csv(DECISION_CSV)

    write_csv(
        APHID_CSV,
        aphid_rows,
        [
            "ts_utc",
            "round_id",
            "request_id",
            "device_id",
            "filename",
            "count",
            "count_mean",
            "aphid_count",
            "slug_count",
            "total_count",
            "class_breakdown_json",
            "images_in_round",
            "aggregation_mode",
            "image_blob_name",
            "history_blob_name",
        ],
    )

    print(f"Generated {len(aphid_rows)} aphid/slug rows at {APHID_CSV}")
    print(
        "Aphid range:",
        min(int(r["aphid_count"]) for r in aphid_rows),
        "to",
        max(int(r["aphid_count"]) for r in aphid_rows),
    )
    print(
        "Slug rows:",
        sum(1 for r in aphid_rows if int(r["slug_count"]) > 0),
        "of",
        len(aphid_rows),
    )

    if not args.write_azure:
        return
    if not args.connection_string:
        raise SystemExit("Missing connection string. Set AZURE_STORAGE_CONNECTION_STRING or pass --connection-string.")

    service = TableServiceClient.from_connection_string(args.connection_string)
    telemetry_table = service.create_table_if_not_exists(args.telemetry_table)
    aphid_table = service.create_table_if_not_exists(args.aphid_table)
    decision_table = service.create_table_if_not_exists(args.decision_table)

    if args.reset:
        print(f"Deleted telemetry rows: {delete_partition(telemetry_table, args.device_id)}")
        print(f"Deleted aphid rows: {delete_partition(aphid_table, args.device_id)}")
        print(f"Deleted decision rows: {delete_partition(decision_table, args.device_id)}")

    upsert_many(telemetry_table, [telemetry_entity(row, args.device_id, i) for i, row in enumerate(telemetry_rows, 1)])
    upsert_many(aphid_table, [aphid_entity(row, i) for i, row in enumerate(aphid_rows, 1)])
    upsert_many(decision_table, [decision_entity(row, args.device_id, i) for i, row in enumerate(decision_rows, 1)])

    print(f"Seeded telemetry rows: {len(telemetry_rows)}")
    print(f"Seeded aphid rows: {len(aphid_rows)}")
    print(f"Seeded decision rows: {len(decision_rows)}")


if __name__ == "__main__":
    main()
