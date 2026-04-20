from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from azure.core.credentials import AzureNamedKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient
from azure.identity import AzureCliCredential
from azure.monitor.ingestion import LogsIngestionClient


CHECKPOINT_PARTITION = "sync"


@dataclass(frozen=True)
class SourceConfig:
    source_table: str
    stream_name: str
    checkpoint_row_key: str


SOURCES = (
    SourceConfig("iottelemetry", "Custom-IoTTelemetryRaw", "iottelemetry"),
    SourceConfig("aphidcounts", "Custom-AphidCountsRaw", "aphidcounts"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Azure Table rows into Log Analytics custom tables.")
    parser.add_argument("--storage-account-name", required=True)
    parser.add_argument("--storage-account-key", default=os.getenv("AZURE_STORAGE_KEY"))
    parser.add_argument("--dcr-endpoint", required=True)
    parser.add_argument("--dcr-immutable-id", required=True)
    parser.add_argument("--checkpoint-table", default="loganalyticssyncstate")
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args()


def normalize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    text = str(value).strip()
    return text or None


def normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def normalize_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def tuple_from_entity(entity: dict[str, Any]) -> tuple[str, str, str]:
    timestamp = normalize_datetime(entity.get("Timestamp")) or ""
    return (timestamp, str(entity.get("PartitionKey", "")), str(entity.get("RowKey", "")))


def load_checkpoint(checkpoint_table, row_key: str) -> tuple[str, str, str]:
    try:
        entity = checkpoint_table.get_entity(partition_key=CHECKPOINT_PARTITION, row_key=row_key)
    except ResourceNotFoundError:
        return ("", "", "")
    return (
        str(entity.get("last_timestamp", "")),
        str(entity.get("last_partition_key", "")),
        str(entity.get("last_row_key", "")),
    )


def save_checkpoint(checkpoint_table, row_key: str, marker: tuple[str, str, str], synced_count: int) -> None:
    entity = {
        "PartitionKey": CHECKPOINT_PARTITION,
        "RowKey": row_key,
        "last_timestamp": marker[0],
        "last_partition_key": marker[1],
        "last_row_key": marker[2],
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "last_synced_count": synced_count,
    }
    checkpoint_table.upsert_entity(entity=entity)


def telemetry_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": entity.get("PartitionKey"),
        "RowKey": entity.get("RowKey"),
        "device_id": entity.get("device_id"),
        "ts": normalize_datetime(entity.get("ts")),
        "temperature": normalize_float(entity.get("temperature")),
        "humidity": normalize_float(entity.get("humidity")),
        "pressure_hpa": normalize_float(entity.get("pressure_hpa")),
        "light": normalize_float(entity.get("light")),
        "created_at": normalize_datetime(entity.get("created_at")),
    }


def aphid_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": entity.get("PartitionKey"),
        "RowKey": entity.get("RowKey"),
        "device_id": entity.get("device_id"),
        "source_device_id": entity.get("source_device_id"),
        "request_id": entity.get("request_id"),
        "ts": normalize_datetime(entity.get("ts")),
        "filename": entity.get("filename"),
        "count": normalize_int(entity.get("count")),
        "image_blob_name": entity.get("image_blob_name"),
        "history_blob_name": entity.get("history_blob_name"),
        "created_at": normalize_datetime(entity.get("created_at")),
    }


def batched(items: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


def sync_source(source_client, checkpoint_table, ingestion_client, args: argparse.Namespace, source: SourceConfig) -> int:
    checkpoint = load_checkpoint(checkpoint_table, source.checkpoint_row_key)
    rows = [entity for entity in source_client.list_entities()]
    rows.sort(key=tuple_from_entity)
    new_rows = [row for row in rows if tuple_from_entity(row) > checkpoint]

    if not new_rows:
        print(f"{source.source_table}: no new rows.")
        return 0

    mapper = telemetry_record if source.source_table == "iottelemetry" else aphid_record
    payload = [mapper(row) for row in new_rows]

    uploaded = 0
    for batch_index, batch in enumerate(batched(payload, args.batch_size)):
        ingestion_client.upload(rule_id=args.dcr_immutable_id, stream_name=source.stream_name, logs=batch)
        uploaded += len(batch)
        marker = tuple_from_entity(new_rows[min(len(new_rows), (batch_index + 1) * args.batch_size) - 1])
        save_checkpoint(checkpoint_table, source.checkpoint_row_key, marker, uploaded)

    print(f"{source.source_table}: synced {uploaded} row(s).")
    return uploaded


def main() -> int:
    args = parse_args()
    if not args.storage_account_key:
        raise SystemExit("Missing storage account key. Pass --storage-account-key or set AZURE_STORAGE_KEY.")

    credential = AzureNamedKeyCredential(args.storage_account_name, args.storage_account_key)
    account_url = f"https://{args.storage_account_name}.table.core.windows.net"
    table_service = TableServiceClient(endpoint=account_url, credential=credential)

    table_service.create_table_if_not_exists(args.checkpoint_table)
    checkpoint_table = table_service.get_table_client(args.checkpoint_table)

    ingestion_client = LogsIngestionClient(args.dcr_endpoint, AzureCliCredential())

    total = 0
    for source in SOURCES:
        source_table = table_service.get_table_client(source.source_table)
        total += sync_source(source_table, checkpoint_table, ingestion_client, args, source)

    print(f"Total synced rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
