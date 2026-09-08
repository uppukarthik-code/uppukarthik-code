# Telemetry: what the tool reads, and how to feed it

The tool consumes exports. It does not collect. This document describes the
vocabulary it expects, the file shapes it accepts, and how to add an adapter for
a particular OEM's export without touching the rules.

## The safety boundary, restated

Readings must come from data the Kavach system has **already recorded and
exported** - a data-logger extract, a remote-monitoring or NMS export, a
maintenance terminal report. Do not write a collector that opens a session to a
Kavach unit. See `INDIAN_CONTEXT.md`.

## Accepted file shapes

**Long CSV** - one reading per row. The easiest shape to produce from any
export, and the shape the simulator writes.

```csv
asset_id,timestamp,metric,value
SKU-EXA,2026-09-08 05:50:00,radio.link_state,UP
SKU-EXA,2026-09-08 05:50:00,radio.rssi_dbm,-62.4
```

**Wide CSV** - one row per asset, one column per metric, with `asset_id` and
optionally `timestamp`.

```csv
asset_id,timestamp,radio.link_state,radio.rssi_dbm
LKU-30201,2026-09-08 05:40:00,UP,-64.2
```

**JSON** - a list of records, an object keyed by asset id, or an object with an
`assets` list:

```json
{"assets": [{"asset_id": "SKU-EXA", "timestamp": "2026-09-08 05:50:00",
             "metrics": {"radio.rssi_dbm": -62.4}}]}
```

A directory may be given instead of a file, in which case every `.csv` and
`.json` inside is read and merged; later files win for the same metric.

Timestamps are accepted in ISO form and in `DD-MM-YYYY HH:MM` form. An asset in
the register with no readings is reported as `KVCH-SYS-001`, not silently
dropped - a unit that stopped reporting is exactly the thing a fleet report
exists to surface.

## Canonical vocabulary

Rules only ever see these names. `kavach-diag metrics` prints the current list.

| Metric | Meaning |
| --- | --- |
| `radio.link_state` | UP / DOWN - Kavach radio link state |
| `radio.rssi_dbm` | Received signal strength, dBm |
| `radio.snr_db` | Signal to noise ratio, dB |
| `radio.vswr` | Antenna VSWR, ratio |
| `radio.tx_power_dbm` | Transmit power, dBm |
| `radio.frequency_mhz` | Operating frequency, MHz |
| `radio.packet_loss_pct` | Radio frame loss over the reporting window, % |
| `radio.time_since_last_frame_s` | Seconds since the last valid frame |
| `radio.peer_units_seen` | Count of Kavach units heard |
| `radio.interference_events_24h` | Interference / noise-floor events in 24 h |
| `rfid.reads_last_run` | Tags successfully read on the last run |
| `rfid.expected_tags_last_run` | Tags the track database expected on that run |
| `rfid.crc_errors` | Tag reads failing the integrity check |
| `rfid.unknown_tag_ids` | Tag identities read that are not in the track database |
| `rfid.last_tag_id`, `rfid.last_tag_km` | Identity and kilometrage of the last tag read |
| `loc.error_m` | Reported location uncertainty, metres |
| `loc.odometer_slip_pct` | Wheel slip/slide detected by odometry, % |
| `time.source`, `time.offset_ms` | Time reference in use and its offset |
| `gnss.fix`, `gnss.satellites` | GNSS fix status and satellites visible |
| `ei.link_state` | UP / DOWN - link to the interlocking |
| `ei.telegram_age_s` | Age of the most recent aspect telegram, seconds |
| `ei.aspect_mismatch_count` | Aspect mismatches against the signal plan |
| `ei.make` | Interlocking make interfaced with |
| `power.mains_state` | OK / FAIL - incoming AC supply |
| `power.charger_state` | FLOAT / BOOST / OFF / FAIL - IPS charger |
| `power.battery_backup_min` | Estimated backup remaining, minutes |
| `power.dc_volts` | DC bus voltage at the unit |
| `kavach.isolation_state`, `kavach.mode` | Onboard isolation and operating mode |
| `dmi.state` | OK / FAIL - Driver Machine Interface |
| `brake.interface_state`, `brake.last_test_result` | Brake interface health |
| `brake.applications_last_24h` | Automatic brake applications in 24 h |
| `sos.messages_24h` | SoS messages recorded in 24 h |
| `sw.version`, `sw.track_db_version` | Software and track database versions |
| `config.checksum` | Checksum of the site configuration |
| `sec.auth_failures_24h` | Message authentication failures in 24 h |
| `sec.key_expiry_days` | Days until the loaded key set expires |
| `sec.unknown_peer_attempts_24h` | Contacts from identities not in the register |
| `sec.maint_port_open` | Maintenance access port enabled |
| `sec.default_credentials` | OEM default credentials still in use |
| `sec.firmware_signed` | Firmware signature verified |
| `sec.usb_events_24h` | Removable-media events on the unit in 24 h |

Booleans are read generously: `true/false`, `yes/no`, `1/0`, `up/down`,
`ok/fail` all work, because exports disagree about this.

Column names are mapped onto the vocabulary by `canonical_metric()`, which
already accepts a few short forms (`rssi`, `vswr`, `track_db`,
`software_version`, `radio_rssi_dbm`). Extend `_SHORT_FORMS` in
`kavach_diag/collectors/base.py` for an OEM whose headings differ.

## Adding an OEM adapter

Subclass `Collector` and return snapshots in the canonical vocabulary. The rules
do not change.

```python
from kavach_diag.collectors import Collector
from kavach_diag.model import Snapshot

class VendorExportCollector(Collector):
    name = "vendor-x"

    def __init__(self, export_path):
        self.export_path = export_path

    def collect(self, assets):
        snapshots = {}
        for record in read_vendor_export(self.export_path):   # your parser
            snapshots[record["unit"]] = Snapshot(
                asset_id=record["unit"],
                recorded_at=record["logged_at"],
                metrics={
                    "radio.rssi_dbm": record["RF_LEVEL"],
                    "radio.link_state": "UP" if record["LINK"] == 1 else "DOWN",
                },
                source=self.name,
            )
        return snapshots
```

Keep the mapping in the collector. A rule that has to know which OEM it is
looking at is a rule that will be wrong for the next one.

## The simulator

`kavach-diag simulate` writes plausible telemetry for a register, so the tool
can be developed, demonstrated and trained on without field data. It is seeded
per asset, so a run is reproducible and filtering the scan to one unit gives the
same readings as scanning the whole register. Use `--as-of` to pin the
timestamps and `--now` on `scan` to reproduce a past run exactly.

Scenarios: `healthy`, `mixed` (default), `degraded`.

The sample data in `data/` is simulated. It is not operational data, and the
zone, division, station and loco identifiers in it are illustrative.
