"""Collector interface and the canonical metric vocabulary.

Every OEM names things differently. Rather than teach the rules engine four
vendor dialects, collectors normalise into the vocabulary below and the rules
only ever see canonical names. Adding a new OEM export therefore means writing
a mapping, not a new rule set.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..model import Asset, Snapshot

# metric name -> what it means and the unit it is expected in.
METRICS: dict[str, str] = {
    # radio
    "radio.link_state": "UP / DOWN - Kavach radio link state",
    "radio.rssi_dbm": "Received signal strength, dBm",
    "radio.snr_db": "Signal to noise ratio, dB",
    "radio.vswr": "Antenna VSWR, ratio",
    "radio.tx_power_dbm": "Transmit power, dBm",
    "radio.frequency_mhz": "Operating frequency, MHz",
    "radio.packet_loss_pct": "Radio frame loss over the reporting window, %",
    "radio.time_since_last_frame_s": "Seconds since the last valid frame",
    "radio.peer_units_seen": "Count of Kavach units heard",
    "radio.interference_events_24h": "Interference / noise-floor events in 24 h",
    # RFID track-side tags
    "rfid.reads_last_run": "Tags successfully read on the last run",
    "rfid.expected_tags_last_run": "Tags the track database expected on that run",
    "rfid.crc_errors": "Tag reads failing the integrity check",
    "rfid.unknown_tag_ids": "Tag identities read that are not in the track database",
    "rfid.last_tag_id": "Identity of the last tag read",
    "rfid.last_tag_km": "Kilometrage of the last tag read",
    # location, odometry and time
    "loc.error_m": "Reported location uncertainty, metres",
    "loc.odometer_slip_pct": "Wheel slip/slide detected by odometry, %",
    "time.source": "GNSS / RTC / NTP - time reference in use",
    "time.offset_ms": "Offset of the unit clock from the reference, ms",
    "gnss.fix": "A (valid) / V (invalid) - GNSS fix status",
    "gnss.satellites": "Satellites visible to the GNSS receiver",
    # interface to the interlocking
    "ei.link_state": "UP / DOWN - link to the electronic interlocking",
    "ei.telegram_age_s": "Age of the most recent aspect telegram, seconds",
    "ei.aspect_mismatch_count": "Aspect mismatches recorded against the signal plan",
    "ei.make": "Interlocking make interfaced with",
    # power supply
    "power.mains_state": "OK / FAIL - incoming AC supply",
    "power.charger_state": "FLOAT / BOOST / OFF / FAIL - IPS charger state",
    "power.battery_backup_min": "Estimated battery backup remaining, minutes",
    "power.dc_volts": "DC bus voltage at the unit, volts",
    # onboard / loco
    "kavach.isolation_state": "NORMAL / ISOLATED - onboard isolation switch",
    "kavach.mode": "Operating mode reported by the loco unit",
    "dmi.state": "OK / FAIL - Driver Machine Interface health",
    "brake.interface_state": "OK / FAIL - brake interface health",
    "brake.last_test_result": "PASS / FAIL - result of the last brake test",
    "brake.applications_last_24h": "Automatic brake applications in 24 h",
    "sos.messages_24h": "SoS messages recorded in 24 h",
    # software and configuration
    "sw.version": "Application software version running on the unit",
    "sw.track_db_version": "Track database version loaded",
    "config.checksum": "Checksum of the site configuration in the unit",
    # security posture
    "sec.auth_failures_24h": "Message authentication failures in 24 h",
    "sec.key_expiry_days": "Days until the loaded key set expires",
    "sec.unknown_peer_attempts_24h": "Contacts from unit identities not in the register",
    "sec.maint_port_open": "true/false - maintenance access port enabled",
    "sec.default_credentials": "true/false - OEM default credentials still in use",
    "sec.firmware_signed": "true/false - firmware signature verified",
    "sec.usb_events_24h": "Removable-media events on the unit in 24 h",
}

# Short forms commonly seen in exports, mapped to the canonical name.
_SHORT_FORMS = {
    "rssi": "radio.rssi_dbm",
    "vswr": "radio.vswr",
    "link_state": "radio.link_state",
    "packet_loss": "radio.packet_loss_pct",
    "frequency": "radio.frequency_mhz",
    "isolation": "kavach.isolation_state",
    "dc_voltage": "power.dc_volts",
    "battery_backup": "power.battery_backup_min",
    "track_db": "sw.track_db_version",
    "software_version": "sw.version",
}


def canonical_metric(name: str) -> str:
    """Map an exported column name onto the canonical vocabulary."""
    key = (name or "").strip()
    if key in METRICS:
        return key
    lowered = key.lower().replace(" ", "_").replace("-", "_")
    if lowered in METRICS:
        return lowered
    if lowered in _SHORT_FORMS:
        return _SHORT_FORMS[lowered]
    # Accept "radio_rssi_dbm" for "radio.rssi_dbm".
    dotted = lowered.replace("__", ".").replace("_", ".", 1)
    if dotted in METRICS:
        return dotted
    return lowered


class Collector(ABC):
    """Produces snapshots for a set of assets."""

    name = "collector"

    @abstractmethod
    def collect(self, assets: list[Asset]) -> dict[str, Snapshot]:
        """Return a snapshot per asset id. Missing assets may be omitted."""

    def snapshot_for(self, assets: list[Asset], asset_id: str) -> Snapshot | None:
        return self.collect(assets).get(asset_id)
