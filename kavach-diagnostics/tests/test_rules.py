import unittest
from datetime import datetime, timedelta

from kavach_diag.config import Settings
from kavach_diag.model import Asset, AssetType, Severity, Snapshot
from kavach_diag.rules import evaluate

NOW = datetime(2026, 9, 8, 6, 0)


def station(**kwargs) -> Asset:
    defaults = dict(
        asset_id="SKU-TEST",
        asset_type=AssetType.SKU,
        station_code="EXA",
        km_post="412/2",
        assigned_freq_mhz="425.0",
        sanctioned_sw_version="4.0.2",
        sanctioned_track_db="TDB-2025-06-R1",
        commissioning_checksum="0x8F31AC20",
    )
    defaults.update(kwargs)
    return Asset(**defaults)


def loco(**kwargs) -> Asset:
    defaults = dict(
        asset_id="LKU-TEST",
        asset_type=AssetType.LKU,
        loco_number="30201",
        loco_class="WAP-7",
        shed_code="EXS",
        sanctioned_track_db="TDB-2025-06-R1",
    )
    defaults.update(kwargs)
    return Asset(**defaults)


def snap(asset_id="SKU-TEST", minutes_old=5, **metrics) -> Snapshot:
    return Snapshot(
        asset_id=asset_id,
        recorded_at=NOW - timedelta(minutes=minutes_old),
        metrics=metrics,
        source="test",
    )


def codes(result) -> set[str]:
    return {f.fault_code for f in result.findings}


class DataAvailabilityTests(unittest.TestCase):
    def test_missing_snapshot_is_reported_once(self):
        result = evaluate(station(), None, now=NOW)
        self.assertEqual(codes(result), {"KVCH-SYS-001"})
        self.assertEqual(result.severity, Severity.NO_DATA)

    def test_empty_snapshot_counts_as_missing(self):
        result = evaluate(station(), Snapshot(asset_id="SKU-TEST"), now=NOW)
        self.assertEqual(codes(result), {"KVCH-SYS-001"})

    def test_stale_snapshot_is_flagged_alongside_other_checks(self):
        result = evaluate(
            station(),
            snap(minutes_old=60 * 40, **{"radio.link_state": "UP", "radio.rssi_dbm": -60}),
            now=NOW,
        )
        self.assertIn("KVCH-SYS-002", codes(result))

    def test_fresh_healthy_unit_reports_ok(self):
        result = evaluate(
            station(),
            snap(**{
                "radio.link_state": "UP",
                "radio.rssi_dbm": -62,
                "radio.vswr": 1.2,
                "radio.packet_loss_pct": 0.4,
                "radio.frequency_mhz": 425.0,
                "ei.link_state": "UP",
                "ei.telegram_age_s": 2,
                "power.mains_state": "OK",
                "power.charger_state": "FLOAT",
                "power.battery_backup_min": 300,
                "power.dc_volts": 26.8,
                "time.source": "GNSS",
                "time.offset_ms": 20,
                "gnss.fix": "A",
                "gnss.satellites": 11,
                "sw.version": "4.0.2",
                "sw.track_db_version": "TDB-2025-06-R1",
                "config.checksum": "0x8F31AC20",
                "sec.key_expiry_days": 200,
            }),
            now=NOW,
        )
        self.assertEqual(codes(result), {"KVCH-OK-000"})
        self.assertEqual(result.severity, Severity.OK)


class ProfileGatingTests(unittest.TestCase):
    def test_loco_is_not_assessed_for_the_interlocking_interface(self):
        result = evaluate(loco(), snap("LKU-TEST", **{"ei.link_state": "DOWN"}), now=NOW)
        self.assertNotIn("KVCH-SIG-001", codes(result))

    def test_tower_is_not_assessed_for_the_brake_interface(self):
        asset = Asset(asset_id="TWR-1", asset_type=AssetType.TWR)
        result = evaluate(asset, snap("TWR-1", **{"brake.interface_state": "FAIL"}), now=NOW)
        self.assertNotIn("KVCH-OBU-003", codes(result))


class RadioRuleTests(unittest.TestCase):
    def test_link_down_suppresses_signal_quality_findings(self):
        result = evaluate(
            station(),
            snap(**{
                "radio.link_state": "DOWN",
                "radio.rssi_dbm": -120,
                "radio.packet_loss_pct": 40,
            }),
            now=NOW,
        )
        self.assertIn("KVCH-RAD-001", codes(result))
        self.assertNotIn("KVCH-RAD-002", codes(result))
        self.assertNotIn("KVCH-RAD-004", codes(result))

    def test_long_radio_silence_counts_as_a_link_failure(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.time_since_last_frame_s": 400}),
            now=NOW,
        )
        self.assertIn("KVCH-RAD-001", codes(result))

    def test_marginal_signal_is_reported_below_major(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -90}),
            now=NOW,
        )
        finding = next(f for f in result.findings if f.fault_code == "KVCH-RAD-002")
        self.assertEqual(finding.severity, Severity.MINOR)

    def test_signal_below_the_working_limit_is_major(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -101}),
            now=NOW,
        )
        finding = next(f for f in result.findings if f.fault_code == "KVCH-RAD-002")
        self.assertEqual(finding.severity, Severity.MAJOR)

    def test_frequency_off_the_assigned_channel(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -60,
                    "radio.frequency_mhz": 426.5}),
            now=NOW,
        )
        self.assertIn("KVCH-RAD-005", codes(result))

    def test_frequency_outside_the_band(self):
        asset = station(assigned_freq_mhz="")
        result = evaluate(
            asset,
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -60,
                    "radio.frequency_mhz": 380.0}),
            now=NOW,
        )
        self.assertIn("KVCH-RAD-005", codes(result))

    def test_interference_needs_a_good_signal_to_be_the_explanation(self):
        weak = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -101,
                    "radio.interference_events_24h": 40,
                    "radio.packet_loss_pct": 9}),
            now=NOW,
        )
        self.assertNotIn("KVCH-RAD-006", codes(weak))

        strong = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -62,
                    "radio.interference_events_24h": 40,
                    "radio.packet_loss_pct": 9}),
            now=NOW,
        )
        self.assertIn("KVCH-RAD-006", codes(strong))


class TagRuleTests(unittest.TestCase):
    def test_shortfall_is_major_and_severe_shortfall_is_critical(self):
        few = evaluate(
            loco(),
            snap("LKU-TEST", **{"rfid.expected_tags_last_run": 100,
                                "rfid.reads_last_run": 92}),
            now=NOW,
        )
        finding = next(f for f in few.findings if f.fault_code == "KVCH-TAG-001")
        self.assertEqual(finding.severity, Severity.MAJOR)

        many = evaluate(
            loco(),
            snap("LKU-TEST", **{"rfid.expected_tags_last_run": 100,
                                "rfid.reads_last_run": 60}),
            now=NOW,
        )
        finding = next(f for f in many.findings if f.fault_code == "KVCH-TAG-001")
        self.assertEqual(finding.severity, Severity.CRITICAL)

    def test_unknown_tag_identity_is_critical(self):
        result = evaluate(
            loco(), snap("LKU-TEST", **{"rfid.unknown_tag_ids": 1}), now=NOW
        )
        self.assertIn("KVCH-TAG-003", codes(result))
        self.assertEqual(result.severity, Severity.CRITICAL)


class SignallingAndPowerTests(unittest.TestCase):
    def test_link_down_suppresses_the_stale_telegram_finding(self):
        result = evaluate(
            station(),
            snap(**{"ei.link_state": "DOWN", "ei.telegram_age_s": 900}),
            now=NOW,
        )
        self.assertIn("KVCH-SIG-001", codes(result))
        self.assertNotIn("KVCH-SIG-002", codes(result))

    def test_mains_failure_and_low_reserve_are_reported_together(self):
        result = evaluate(
            station(),
            snap(**{"power.mains_state": "FAIL", "power.charger_state": "FAIL",
                    "power.battery_backup_min": 30, "power.dc_volts": 20.1}),
            now=NOW,
        )
        self.assertTrue({"KVCH-PWR-001", "KVCH-PWR-002", "KVCH-PWR-003",
                         "KVCH-PWR-004"} <= codes(result))

    def test_dc_range_follows_the_asset_type(self):
        onboard = evaluate(loco(), snap("LKU-TEST", **{"power.dc_volts": 110}), now=NOW)
        self.assertNotIn("KVCH-PWR-004", codes(onboard))


class OnboardAndConfigTests(unittest.TestCase):
    def test_isolation_is_critical(self):
        result = evaluate(
            loco(), snap("LKU-TEST", **{"kavach.isolation_state": "ISOLATED"}), now=NOW
        )
        self.assertIn("KVCH-OBU-001", codes(result))
        self.assertEqual(result.severity, Severity.CRITICAL)

    def test_track_database_mismatch_against_the_register(self):
        result = evaluate(
            loco(), snap("LKU-TEST", **{"sw.track_db_version": "TDB-2024-11-R3"}), now=NOW
        )
        self.assertIn("KVCH-CFG-001", codes(result))

    def test_matching_versions_raise_nothing(self):
        result = evaluate(
            loco(), snap("LKU-TEST", **{"sw.track_db_version": "TDB-2025-06-R1"}), now=NOW
        )
        self.assertNotIn("KVCH-CFG-001", codes(result))


class SecurityRuleTests(unittest.TestCase):
    def test_auth_failures_on_a_poor_link_are_downgraded(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -101,
                    "sec.auth_failures_24h": 8}),
            now=NOW,
        )
        finding = next(f for f in result.findings if f.fault_code == "KVCH-SEC-001")
        self.assertEqual(finding.severity, Severity.MINOR)
        self.assertIn("corruption", finding.likely_cause)

    def test_auth_failures_on_a_good_link_stay_major(self):
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -60,
                    "sec.auth_failures_24h": 8}),
            now=NOW,
        )
        finding = next(f for f in result.findings if f.fault_code == "KVCH-SEC-001")
        self.assertEqual(finding.severity, Severity.MAJOR)

    def test_expired_key_set_is_escalated_to_critical(self):
        result = evaluate(station(), snap(**{"sec.key_expiry_days": 0}), now=NOW)
        finding = next(f for f in result.findings if f.fault_code == "KVCH-SEC-002")
        self.assertEqual(finding.severity, Severity.CRITICAL)

    def test_default_credentials_and_unsigned_firmware_are_critical(self):
        result = evaluate(
            station(),
            snap(**{"sec.default_credentials": "true", "sec.firmware_signed": "false"}),
            now=NOW,
        )
        self.assertTrue({"KVCH-SEC-005", "KVCH-SEC-006"} <= codes(result))


class SettingsTests(unittest.TestCase):
    def test_ignored_codes_are_suppressed(self):
        settings = Settings(ignore_codes=("KVCH-RAD-002",))
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -101}),
            settings=settings,
            now=NOW,
        )
        self.assertNotIn("KVCH-RAD-002", codes(result))

    def test_thresholds_can_be_tightened(self):
        settings = Settings()
        settings.thresholds.rssi_marginal_dbm = -50.0
        settings.thresholds.rssi_min_dbm = -55.0
        result = evaluate(
            station(),
            snap(**{"radio.link_state": "UP", "radio.rssi_dbm": -60}),
            settings=settings,
            now=NOW,
        )
        self.assertIn("KVCH-RAD-002", codes(result))


if __name__ == "__main__":
    unittest.main()
