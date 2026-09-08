"""A telemetry simulator, so the tool can be exercised without field data.

Operational Kavach data cannot be published, and a diagnostic tool that can
only be demonstrated on a live safety system is not much use for development or
training. The simulator produces plausible readings in the canonical vocabulary
for a given asset register, seeded so that a run is reproducible.

Scenario profiles:

* ``healthy``  - everything within limits.
* ``mixed``    - the default; a realistic scatter of faults across the section.
* ``degraded`` - a bad day: several critical conditions, for report testing.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from ..config import profile_for
from ..model import Asset, Snapshot
from .base import Collector

SCENARIOS = ("healthy", "mixed", "degraded")

# Fault injections, each a callable applied to a metrics dict.
FAULT_INJECTIONS: dict[str, callable] = {
    "radio_down": lambda m: m.update(
        {"radio.link_state": "DOWN", "radio.time_since_last_frame_s": 412,
         "radio.rssi_dbm": -120, "radio.peer_units_seen": 0}
    ),
    "weak_rssi": lambda m: m.update(
        {"radio.rssi_dbm": -101, "radio.packet_loss_pct": 6.4, "radio.snr_db": 4}
    ),
    "high_vswr": lambda m: m.update({"radio.vswr": 2.4}),
    "interference": lambda m: m.update(
        {"radio.interference_events_24h": 37, "radio.packet_loss_pct": 8.1,
         "sec.auth_failures_24h": 12}
    ),
    "tag_miss": lambda m: m.update(
        {"rfid.reads_last_run": 108, "rfid.expected_tags_last_run": 126,
         "rfid.crc_errors": 4}
    ),
    "unknown_tag": lambda m: m.update(
        {"rfid.unknown_tag_ids": 1, "rfid.last_tag_id": "TAG-UNREGISTERED-4471"}
    ),
    "location_error": lambda m: m.update(
        {"loc.error_m": 41.2, "loc.odometer_slip_pct": 7.8}
    ),
    "time_drift": lambda m: m.update(
        {"time.source": "RTC", "time.offset_ms": 4200, "gnss.fix": "V",
         "gnss.satellites": 0}
    ),
    "ei_down": lambda m: m.update(
        {"ei.link_state": "DOWN", "ei.telegram_age_s": 900}
    ),
    "aspect_mismatch": lambda m: m.update({"ei.aspect_mismatch_count": 2}),
    "mains_fail": lambda m: m.update(
        {"power.mains_state": "FAIL", "power.charger_state": "OFF",
         "power.battery_backup_min": 74}
    ),
    "battery_low": lambda m: m.update(
        {"power.mains_state": "FAIL", "power.charger_state": "FAIL",
         "power.battery_backup_min": 22, "power.dc_volts": 20.4}
    ),
    "isolated": lambda m: m.update(
        {"kavach.isolation_state": "ISOLATED", "kavach.mode": "ISOLATED"}
    ),
    "brake_fault": lambda m: m.update(
        {"brake.interface_state": "FAIL", "brake.last_test_result": "FAIL"}
    ),
    "dmi_fault": lambda m: m.update({"dmi.state": "FAIL"}),
    "track_db_stale": lambda m: m.update({"sw.track_db_version": "TDB-2024-11-R3"}),
    "default_creds": lambda m: m.update(
        {"sec.default_credentials": "true", "sec.maint_port_open": "true"}
    ),
    "key_expiry": lambda m: m.update({"sec.key_expiry_days": 9}),
    "unsigned_fw": lambda m: m.update({"sec.firmware_signed": "false"}),
    "unknown_peer": lambda m: m.update({"sec.unknown_peer_attempts_24h": 3}),
    "usb_events": lambda m: m.update({"sec.usb_events_24h": 2}),
}

# Which injections make sense for which asset type.
INJECTIONS_BY_TYPE = {
    "SKU": ["radio_down", "weak_rssi", "high_vswr", "interference", "ei_down",
            "aspect_mismatch", "mains_fail", "battery_low", "track_db_stale",
            "default_creds", "key_expiry", "unknown_peer", "usb_events"],
    "LKU": ["weak_rssi", "tag_miss", "unknown_tag", "location_error", "time_drift",
            "isolated", "brake_fault", "dmi_fault", "track_db_stale", "unsigned_fw",
            "usb_events"],
    "TWR": ["radio_down", "high_vswr", "weak_rssi", "mains_fail", "interference"],
    "RIU": ["ei_down", "aspect_mismatch", "mains_fail", "key_expiry"],
}

FAULT_RATES = {"healthy": 0.0, "mixed": 0.35, "degraded": 0.75}


def _healthy_metrics(asset: Asset, rng: random.Random) -> dict[str, object]:
    checks = profile_for(asset.asset_type).checks
    metrics: dict[str, object] = {}

    if "radio" in checks:
        metrics.update({
            "radio.link_state": "UP",
            "radio.rssi_dbm": round(rng.uniform(-78, -58), 1),
            "radio.snr_db": round(rng.uniform(14, 26), 1),
            "radio.vswr": round(rng.uniform(1.05, 1.32), 2),
            "radio.tx_power_dbm": 37,
            "radio.frequency_mhz": asset.assigned_freq_mhz or 425.0,
            "radio.packet_loss_pct": round(rng.uniform(0.0, 0.9), 2),
            "radio.time_since_last_frame_s": rng.randint(1, 6),
            "radio.peer_units_seen": rng.randint(2, 9),
            "radio.interference_events_24h": rng.randint(0, 2),
        })
    if "rfid" in checks:
        expected = rng.randint(90, 160)
        metrics.update({
            "rfid.expected_tags_last_run": expected,
            "rfid.reads_last_run": expected,
            "rfid.crc_errors": 0,
            "rfid.unknown_tag_ids": 0,
            "rfid.last_tag_id": f"TAG-{rng.randint(10000, 99999)}",
            "rfid.last_tag_km": f"{rng.randint(120, 480)}/{rng.choice([0, 2, 4, 6, 8])}",
        })
    if "location" in checks:
        metrics.update({
            "loc.error_m": round(rng.uniform(1.2, 6.5), 1),
            "loc.odometer_slip_pct": round(rng.uniform(0.0, 1.8), 2),
        })
    if "time" in checks:
        metrics.update({
            "time.source": "GNSS",
            "time.offset_ms": rng.randint(1, 60),
            "gnss.fix": "A",
            "gnss.satellites": rng.randint(8, 16),
        })
    if "signalling" in checks:
        metrics.update({
            "ei.link_state": "UP",
            "ei.telegram_age_s": rng.randint(1, 4),
            "ei.aspect_mismatch_count": 0,
            "ei.make": rng.choice(["EI-A", "EI-B", "RRI"]),
        })
    if "power" in checks:
        onboard = asset.asset_type == "LKU"
        metrics.update({
            "power.mains_state": "OK",
            "power.charger_state": "FLOAT",
            "power.battery_backup_min": rng.randint(180, 480),
            "power.dc_volts": round(
                rng.uniform(108, 118) if onboard else rng.uniform(25.8, 27.6), 1
            ),
        })
    if "onboard" in checks:
        metrics.update({
            "kavach.isolation_state": "NORMAL",
            "kavach.mode": "FULL SUPERVISION",
            "dmi.state": "OK",
            "brake.interface_state": "OK",
            "brake.last_test_result": "PASS",
            "brake.applications_last_24h": rng.choice([0, 0, 0, 1]),
            "sos.messages_24h": 0,
        })
    if "config" in checks:
        metrics.update({
            "sw.version": asset.sanctioned_sw_version or "4.0.2",
            "sw.track_db_version": asset.sanctioned_track_db or "TDB-2025-06-R1",
            "config.checksum": asset.commissioning_checksum or "0x8F31AC20",
        })
    if "security" in checks:
        metrics.update({
            "sec.auth_failures_24h": 0,
            "sec.key_expiry_days": rng.randint(120, 330),
            "sec.unknown_peer_attempts_24h": 0,
            "sec.maint_port_open": "false",
            "sec.default_credentials": "false",
            "sec.firmware_signed": "true",
            "sec.usb_events_24h": 0,
        })
    return metrics


class SimulatedCollector(Collector):
    """Generates telemetry for an asset register."""

    name = "simulator"

    def __init__(
        self,
        scenario: str = "mixed",
        seed: int = 20250908,
        now: datetime | None = None,
    ):
        if scenario not in SCENARIOS:
            raise ValueError(
                f"Unknown scenario {scenario!r}; choose from {', '.join(SCENARIOS)}"
            )
        self.scenario = scenario
        self.seed = seed
        self.now = now

    def collect(self, assets: list[Asset]) -> dict[str, Snapshot]:
        rate = FAULT_RATES[self.scenario]
        now = (self.now or datetime.now()).replace(microsecond=0)
        snapshots: dict[str, Snapshot] = {}

        for asset in assets:
            # Seeded per asset, so filtering the scan to a few units gives the
            # same readings as scanning the whole register.
            rng = random.Random(f"{self.seed}:{self.scenario}:{asset.asset_id}")
            # In a real export a few units are simply absent.
            if self.scenario != "healthy" and rng.random() < 0.05:
                continue

            metrics = _healthy_metrics(asset, rng)
            candidates = INJECTIONS_BY_TYPE.get(asset.asset_type, [])
            if candidates and rng.random() < rate:
                for name in rng.sample(candidates, k=rng.choice([1, 1, 2])):
                    FAULT_INJECTIONS[name](metrics)

            recorded_at = now - timedelta(minutes=rng.randint(2, 90))
            if self.scenario == "degraded" and rng.random() < 0.15:
                recorded_at = now - timedelta(hours=rng.randint(30, 100))

            snapshots[asset.asset_id] = Snapshot(
                asset_id=asset.asset_id,
                recorded_at=recorded_at,
                metrics=metrics,
                source=f"simulator:{self.scenario}",
            )
        return snapshots


def write_simulated_telemetry(
    assets: list[Asset],
    output: str | Path,
    scenario: str = "mixed",
    seed: int = 20250908,
    now: datetime | None = None,
) -> Path:
    """Write simulated telemetry as a long-form CSV and return the path."""
    snapshots = SimulatedCollector(scenario=scenario, seed=seed, now=now).collect(assets)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["asset_id", "timestamp", "metric", "value"])
        for asset in assets:
            snapshot = snapshots.get(asset.asset_id)
            if snapshot is None:
                continue
            stamp = (
                snapshot.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
                if snapshot.recorded_at
                else ""
            )
            for metric, value in snapshot.metrics.items():
                writer.writerow([asset.asset_id, stamp, metric, value])
    return output
