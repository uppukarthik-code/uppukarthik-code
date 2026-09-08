"""Thresholds and asset profiles used by the diagnostic engine.

Everything the rules compare against lives here so that a division can tune the
tool to its own installation without touching rule logic. Values are working
defaults for a first-line diagnostic aid; they are not a substitute for the
limits in the applicable RDSO specification, the OEM maintenance handbook or
the division's own instructions. Confirm each limit before field use.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .model import AssetType


@dataclass
class Thresholds:
    # ---- radio -------------------------------------------------------
    rssi_min_dbm: float = -95.0
    rssi_marginal_dbm: float = -85.0
    vswr_max: float = 1.5
    packet_loss_max_pct: float = 2.0
    radio_silence_max_s: float = 30.0
    # Kavach radio works in the UHF band allotted to Indian Railways.
    radio_band_mhz: tuple[float, float] = (405.0, 450.0)
    interference_events_threshold: int = 5

    # ---- RFID tags ---------------------------------------------------
    tag_read_min_ratio: float = 0.95
    tag_crc_errors_max: int = 0

    # ---- location and time -------------------------------------------
    location_error_max_m: float = 15.0
    odometer_slip_max_pct: float = 5.0
    time_offset_max_ms: float = 1000.0

    # ---- signalling interface ----------------------------------------
    telegram_age_max_s: float = 10.0

    # ---- power -------------------------------------------------------
    battery_backup_min_minutes: float = 120.0
    dc_volts_range: tuple[float, float] = (21.6, 29.0)

    # ---- onboard -----------------------------------------------------
    brake_applications_review: int = 3

    # ---- security ----------------------------------------------------
    auth_failures_threshold: int = 0
    key_expiry_notice_days: int = 30
    unknown_peer_threshold: int = 0

    # ---- data freshness ----------------------------------------------
    snapshot_stale_after_hours: float = 24.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["radio_band_mhz"] = list(self.radio_band_mhz)
        data["dc_volts_range"] = list(self.dc_volts_range)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Thresholds":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        for key in ("radio_band_mhz", "dc_volts_range"):
            if key in clean and isinstance(clean[key], list):
                clean[key] = tuple(clean[key])
        return cls(**clean)

    @classmethod
    def load(cls, path: str | Path | None) -> "Thresholds":
        if not path:
            return cls()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)


@dataclass
class AssetProfile:
    """Which check families apply to a given Kavach asset type.

    A loco unit has no interlocking interface; a tower has no brake interface.
    Without profiles the engine would report a stream of false failures, which
    is exactly what makes a fleet-wide report get ignored.
    """

    checks: tuple[str, ...] = ()
    dc_volts_range: tuple[float, float] | None = None
    description: str = ""


ASSET_PROFILES: dict[str, AssetProfile] = {
    AssetType.SKU: AssetProfile(
        checks=("radio", "signalling", "power", "config", "security", "time"),
        dc_volts_range=(21.6, 29.0),
        description=(
            "Station unit: radio to locos and neighbouring units, interface to "
            "the interlocking, and IPS-fed power."
        ),
    ),
    AssetType.LKU: AssetProfile(
        checks=("radio", "rfid", "location", "onboard", "config", "security", "time"),
        dc_volts_range=(90.0, 130.0),  # loco control supply
        description=(
            "Loco unit: radio, RFID reading, odometry, brake interface and DMI."
        ),
    ),
    AssetType.TWR: AssetProfile(
        checks=("radio", "power", "security"),
        dc_volts_range=(21.6, 29.0),
        description="Radio tower / static radio unit: radio path and supply only.",
    ),
    AssetType.RIU: AssetProfile(
        checks=("signalling", "power", "config", "security"),
        dc_volts_range=(21.6, 29.0),
        description="Remote interface unit: signalling interface and supply.",
    ),
}

DEFAULT_PROFILE = AssetProfile(
    checks=("radio", "power", "security"),
    description="Fallback profile for an asset type not in the register.",
)


def profile_for(asset_type: str) -> AssetProfile:
    return ASSET_PROFILES.get((asset_type or "").upper(), DEFAULT_PROFILE)


@dataclass
class Settings:
    thresholds: Thresholds = field(default_factory=Thresholds)
    ignore_codes: tuple[str, ...] = ()

    def dc_range_for(self, asset_type: str) -> tuple[float, float]:
        profile = profile_for(asset_type)
        return profile.dc_volts_range or self.thresholds.dc_volts_range
