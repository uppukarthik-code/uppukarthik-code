"""Reading telemetry that has already been exported to file.

Two shapes are supported, because that is what monitoring systems produce:

* **Long CSV** - ``asset_id,timestamp,metric,value``, one reading per row. This
  is what falls out of most remote-monitoring exports and is easy to produce
  from a data-logger dump with a short script.
* **Wide CSV** - one row per asset, one column per metric, with ``asset_id``
  and optionally ``timestamp`` columns.
* **JSON** - either a list of ``{"asset_id": ..., "metrics": {...}}`` objects
  or an object keyed by asset id.

A directory may be passed, in which case every supported file inside it is read
and later readings win over earlier ones for the same metric.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from ..model import Asset, Snapshot
from .base import Collector, canonical_metric

TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d",
)

LONG_FORM_COLUMNS = {"metric", "value"}


class TelemetryError(ValueError):
    """Raised when a telemetry file cannot be interpreted."""


def parse_timestamp(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "")
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _blank(headers) -> dict[str, str]:
    return {h.strip().lower(): h for h in headers if h}


def _read_csv(path: Path, into: dict[str, Snapshot]) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise TelemetryError(f"{path}: no header row")
        headers = _blank(reader.fieldnames)
        if "asset_id" not in headers:
            raise TelemetryError(f"{path}: an 'asset_id' column is required")
        long_form = LONG_FORM_COLUMNS.issubset(headers)

        for row in reader:
            clean = {
                (k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k
            }
            asset_id = clean.get("asset_id", "")
            if not asset_id:
                continue
            snapshot = into.setdefault(
                asset_id, Snapshot(asset_id=asset_id, source=str(path))
            )
            stamp = parse_timestamp(clean.get("timestamp"))
            if stamp and (snapshot.recorded_at is None or stamp > snapshot.recorded_at):
                snapshot.recorded_at = stamp

            if long_form:
                metric = canonical_metric(clean.get("metric", ""))
                if metric:
                    snapshot.metrics[metric] = clean.get("value", "")
            else:
                for column, value in clean.items():
                    if column in ("asset_id", "timestamp") or value in ("", None):
                        continue
                    snapshot.metrics[canonical_metric(column)] = value


def _read_json(path: Path, into: dict[str, Snapshot]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict) and "assets" in data:
        data = data["assets"]

    records: list[dict] = []
    if isinstance(data, list):
        records = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        for asset_id, payload in data.items():
            if isinstance(payload, dict):
                record = dict(payload)
                record.setdefault("asset_id", asset_id)
                records.append(record)
    else:
        raise TelemetryError(f"{path}: unsupported JSON structure")

    for record in records:
        asset_id = str(record.get("asset_id", "")).strip()
        if not asset_id:
            continue
        snapshot = into.setdefault(
            asset_id, Snapshot(asset_id=asset_id, source=str(path))
        )
        stamp = parse_timestamp(record.get("timestamp"))
        if stamp and (snapshot.recorded_at is None or stamp > snapshot.recorded_at):
            snapshot.recorded_at = stamp
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {
                k: v for k, v in record.items() if k not in ("asset_id", "timestamp")
            }
        for key, value in metrics.items():
            snapshot.metrics[canonical_metric(key)] = value


def load_snapshots(path: str | Path) -> dict[str, Snapshot]:
    """Load every supported telemetry file at ``path`` (file or directory)."""
    path = Path(path)
    if not path.exists():
        raise TelemetryError(f"Telemetry path not found: {path}")

    files: list[Path]
    if path.is_dir():
        files = sorted(
            p
            for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in (".csv", ".json")
        )
        if not files:
            raise TelemetryError(f"No .csv or .json telemetry files in {path}")
    else:
        files = [path]

    snapshots: dict[str, Snapshot] = {}
    for file in files:
        if file.suffix.lower() == ".json":
            _read_json(file, snapshots)
        else:
            _read_csv(file, snapshots)
    return snapshots


class FileCollector(Collector):
    """Collector backed by exported telemetry files."""

    name = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._cache: dict[str, Snapshot] | None = None

    def collect(self, assets: list[Asset]) -> dict[str, Snapshot]:
        if self._cache is None:
            self._cache = load_snapshots(self.path)
        return self._cache
