"""Loading the divisional Kavach asset register.

The register is a CSV so that it can be maintained by the division in the same
way an S&T asset list already is. Column names are matched case-insensitively
and a few common alternatives are accepted, because real registers are rarely
typed to a schema.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .model import Asset, AssetType

# Alternative column headings seen in divisional asset lists.
ALIASES = {
    "asset_id": ("asset", "unit_id", "id", "unit"),
    "asset_type": ("type", "unit_type", "kavach_type"),
    "kavach_id": ("kavach_unit_id", "unit_number", "kavach_no"),
    "station_code": ("stn_code", "station", "stn"),
    "station_name": ("stn_name", "name"),
    "km_post": ("km", "kmp", "chainage", "location_km"),
    "loco_number": ("loco_no", "loco", "engine_no"),
    "loco_class": ("loco_type", "class"),
    "shed_code": ("shed", "home_shed"),
    "spec_version": ("kavach_version", "spec"),
    "commissioned_on": ("commissioning_date", "cod", "date_of_commissioning"),
    "assigned_freq_mhz": ("frequency_mhz", "assigned_frequency", "channel_mhz"),
    "sanctioned_sw_version": ("approved_sw_version", "sw_version_sanctioned"),
    "sanctioned_track_db": ("track_db_version", "approved_track_db"),
    "commissioning_checksum": ("config_checksum_commissioned", "baseline_checksum"),
}

FIELDS = set(Asset.__dataclass_fields__)


class InventoryError(ValueError):
    """Raised when the register cannot be used as supplied."""


def _normalise_row(row: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        # Strip a UTF-8 BOM and normalise spacing/case in the heading.
        name = key.replace("﻿", "").strip().lower().replace(" ", "_")
        clean[name] = (value or "").strip()

    mapped: dict[str, str] = {}
    for field_name in FIELDS:
        if field_name in clean:
            mapped[field_name] = clean[field_name]
            continue
        for alias in ALIASES.get(field_name, ()):
            if alias in clean:
                mapped[field_name] = clean[alias]
                break
    return mapped


def load_inventory(path: str | Path) -> list[Asset]:
    """Read the asset register, returning assets in file order."""
    path = Path(path)
    if not path.exists():
        raise InventoryError(f"Inventory file not found: {path}")

    assets: list[Asset] = []
    seen: set[str] = set()

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise InventoryError(f"Inventory file has no header row: {path}")

        for line_no, row in enumerate(reader, start=2):
            mapped = _normalise_row(row)
            asset_id = mapped.get("asset_id", "")
            if not asset_id:
                continue  # blank filler row
            if asset_id in seen:
                raise InventoryError(
                    f"Duplicate asset_id {asset_id!r} at line {line_no} of {path}"
                )
            asset_type = mapped.get("asset_type", "").upper()
            if asset_type not in AssetType.ALL:
                raise InventoryError(
                    f"Line {line_no}: asset_type {asset_type!r} for {asset_id} is not "
                    f"one of {', '.join(AssetType.ALL)}"
                )
            seen.add(asset_id)
            assets.append(Asset(**mapped))

    if not assets:
        raise InventoryError(f"No assets found in {path}")
    return assets


def summarise(assets: list[Asset]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset in assets:
        counts[asset.asset_type] = counts.get(asset.asset_type, 0) + 1
    return counts
