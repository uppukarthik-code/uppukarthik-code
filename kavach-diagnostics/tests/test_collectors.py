import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kavach_diag.collectors import canonical_metric, load_snapshots
from kavach_diag.collectors.file_collector import TelemetryError, parse_timestamp
from kavach_diag.collectors.simulator import SimulatedCollector
from kavach_diag.inventory import load_inventory

DATA = Path(__file__).resolve().parents[1] / "data"
REGISTER = DATA / "inventory/example_division_register.csv"


class MetricNameTests(unittest.TestCase):
    def test_canonical_names_pass_through(self):
        self.assertEqual(canonical_metric("radio.rssi_dbm"), "radio.rssi_dbm")

    def test_short_forms_are_mapped(self):
        self.assertEqual(canonical_metric("RSSI"), "radio.rssi_dbm")
        self.assertEqual(canonical_metric("track_db"), "sw.track_db_version")

    def test_underscore_form_is_mapped(self):
        self.assertEqual(canonical_metric("radio_rssi_dbm"), "radio.rssi_dbm")


class FileCollectorTests(unittest.TestCase):
    def test_long_form_csv(self):
        snapshots = load_snapshots(DATA / "telemetry/section_scan_mixed.csv")
        self.assertEqual(len(snapshots), 20)
        self.assertIn("radio.link_state", snapshots["SKU-EXA"].metrics)

    def test_wide_form_csv(self):
        snapshots = load_snapshots(DATA / "telemetry/loco_export_wide.csv")
        loco = snapshots["LKU-40077"]
        self.assertEqual(loco.upper("kavach.isolation_state"), "ISOLATED")
        self.assertIs(loco.flag("sec.maint_port_open"), True)

    def test_json_export(self):
        snapshots = load_snapshots(DATA / "telemetry/station_export.json")
        self.assertEqual(sorted(snapshots), ["SKU-EXA", "SKU-EXD"])
        self.assertEqual(snapshots["SKU-EXD"].upper("power.mains_state"), "FAIL")

    def test_directory_merges_every_file(self):
        snapshots = load_snapshots(DATA / "telemetry")
        self.assertGreaterEqual(len(snapshots), 20)

    def test_timestamp_formats(self):
        for text in ("2026-09-08 06:00:00", "08-09-2026 06:00", "2026-09-08T06:00:00"):
            self.assertIsNotNone(parse_timestamp(text), text)
        self.assertIsNone(parse_timestamp("not a date"))

    def test_missing_asset_id_column_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("train,metric,value\nA,radio.rssi_dbm,-60\n", encoding="utf-8")
            with self.assertRaises(TelemetryError):
                load_snapshots(path)

    def test_json_keyed_by_asset_id(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "keyed.json"
            path.write_text(
                json.dumps({"SKU-EXA": {"metrics": {"radio.rssi_dbm": -70}}}),
                encoding="utf-8",
            )
            snapshots = load_snapshots(path)
        self.assertEqual(snapshots["SKU-EXA"].number("radio.rssi_dbm"), -70.0)


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.assets = load_inventory(REGISTER)

    def test_healthy_scenario_reports_every_asset(self):
        snapshots = SimulatedCollector("healthy").collect(self.assets)
        self.assertEqual(len(snapshots), len(self.assets))

    def test_seeded_runs_are_reproducible(self):
        first = SimulatedCollector("mixed", seed=7).collect(self.assets)
        second = SimulatedCollector("mixed", seed=7).collect(self.assets)
        self.assertEqual(
            {k: v.metrics for k, v in first.items()},
            {k: v.metrics for k, v in second.items()},
        )

    def test_readings_do_not_depend_on_the_rest_of_the_register(self):
        one = self.assets[:1]
        full = SimulatedCollector("mixed").collect(self.assets)
        single = SimulatedCollector("mixed").collect(one)
        self.assertEqual(
            single[one[0].asset_id].metrics, full[one[0].asset_id].metrics
        )

    def test_profiles_decide_which_metrics_exist(self):
        snapshots = SimulatedCollector("healthy").collect(self.assets)
        tower = snapshots["TWR-EXA1"]
        loco = snapshots["LKU-30201"]
        self.assertNotIn("ei.link_state", tower.metrics)
        self.assertNotIn("brake.interface_state", tower.metrics)
        self.assertIn("rfid.reads_last_run", loco.metrics)

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            SimulatedCollector("catastrophic")


if __name__ == "__main__":
    unittest.main()
