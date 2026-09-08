import csv
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from kavach_diag import cli, report
from kavach_diag.inventory import load_inventory
from kavach_diag.model import Asset, AssetType, Severity, Snapshot
from kavach_diag.rules import evaluate, evaluate_all

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "data/inventory/example_division_register.csv"
TELEMETRY = ROOT / "data/telemetry/section_scan_mixed.csv"
NOW = datetime(2026, 9, 8, 6, 0)


def sample_results():
    assets = load_inventory(REGISTER)
    snapshots = {
        "SKU-EXA": Snapshot(
            asset_id="SKU-EXA",
            recorded_at=NOW - timedelta(minutes=10),
            metrics={"radio.link_state": "DOWN", "power.mains_state": "OK"},
            source="test",
        )
    }
    return evaluate_all(assets[:3], snapshots, now=NOW)


class TextReportTests(unittest.TestCase):
    def test_asset_report_carries_evidence_and_action(self):
        asset = Asset(
            asset_id="SKU-EXA",
            asset_type=AssetType.SKU,
            station_code="EXA",
            station_name="Example A Jn",
            km_post="412/2",
        )
        snapshot = Snapshot(
            asset_id="SKU-EXA",
            recorded_at=NOW,
            metrics={"radio.link_state": "DOWN"},
            source="test",
        )
        text = report.render_asset_report(evaluate(asset, snapshot, now=NOW))
        self.assertIn("KVCH-RAD-001", text)
        self.assertIn("EXA - Example A Jn / KM 412/2", text)
        self.assertIn("Likely cause", text)
        self.assertIn("Escalation", text)

    def test_summary_lists_assets_needing_attention(self):
        text = report.render_summary(sample_results())
        self.assertIn("SCAN SUMMARY", text)
        self.assertIn("REQUIRING ATTENTION", text)
        self.assertIn("SKU-EXA", text)

    def test_summary_says_so_when_nothing_is_wrong(self):
        asset = Asset(asset_id="TWR-1", asset_type=AssetType.TWR)
        snapshot = Snapshot(
            asset_id="TWR-1",
            recorded_at=NOW,
            metrics={"radio.link_state": "UP", "radio.rssi_dbm": -60},
        )
        text = report.render_summary([evaluate(asset, snapshot, now=NOW)])
        self.assertIn("No critical or major conditions", text)


class FileReportTests(unittest.TestCase):
    def test_csv_has_one_row_per_finding(self):
        results = sample_results()
        with TemporaryDirectory() as tmp:
            path = report.write_csv(results, Path(tmp) / "scan.csv")
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), sum(len(r.findings) for r in results))
        self.assertEqual(rows[0]["asset_id"], "SKU-EXA")
        self.assertIn("recommended_action", rows[0])

    def test_html_report_is_self_contained(self):
        with TemporaryDirectory() as tmp:
            path = report.write_html(sample_results(), Path(tmp) / "health.html")
            document = path.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", document)
        self.assertNotIn("<script", document)
        self.assertIn("KVCH-RAD-001", document)
        self.assertIn("prefers-color-scheme", document)

    def test_html_escapes_values_from_the_register(self):
        asset = Asset(
            asset_id="SKU-<script>",
            asset_type=AssetType.SKU,
            station_code="EXA",
        )
        results = [evaluate(asset, None, now=NOW)]
        with TemporaryDirectory() as tmp:
            path = report.write_html(results, Path(tmp) / "health.html")
            document = path.read_text(encoding="utf-8")
        self.assertNotIn("SKU-<script>", document)
        self.assertIn("SKU-&lt;script&gt;", document)


class CliTests(unittest.TestCase):
    def test_scan_from_file_reports_findings(self):
        with TemporaryDirectory() as tmp:
            code = cli.main([
                "scan",
                "--inventory", str(REGISTER),
                "--telemetry", str(TELEMETRY),
                "--now", "2026-09-08 06:00",
                "--out", tmp,
                "--format", "csv,html",
            ])
            written = sorted(p.name for p in Path(tmp).iterdir())
        self.assertEqual(code, cli.EXIT_FINDINGS)
        self.assertEqual(len(written), 2)

    def test_healthy_scan_exits_zero(self):
        with TemporaryDirectory() as tmp:
            code = cli.main([
                "scan",
                "--inventory", str(REGISTER),
                "--telemetry", str(ROOT / "data/telemetry/section_scan_healthy.csv"),
                "--now", "2026-09-08 06:00",
                "--out", tmp,
                "--format", "text",
            ])
        self.assertEqual(code, cli.EXIT_OK)

    def test_scan_without_a_source_is_an_error(self):
        code = cli.main(["scan", "--inventory", str(REGISTER)])
        self.assertEqual(code, cli.EXIT_ERROR)

    def test_unknown_fault_code_is_an_error(self):
        self.assertEqual(cli.main(["explain", "KVCH-XXX-999"]), cli.EXIT_ERROR)

    def test_explain_known_code(self):
        self.assertEqual(cli.main(["explain", "kvch-rad-002"]), cli.EXIT_OK)

    def test_simulate_writes_telemetry(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "telemetry.csv"
            code = cli.main([
                "simulate",
                "--inventory", str(REGISTER),
                "--out", str(out),
                "--scenario", "degraded",
                "--as-of", "2026-09-08 06:00",
            ])
        self.assertEqual(code, cli.EXIT_OK)

    def test_bad_now_value_is_reported(self):
        code = cli.main([
            "scan",
            "--inventory", str(REGISTER),
            "--simulate", "healthy",
            "--now", "yesterday",
        ])
        self.assertEqual(code, cli.EXIT_ERROR)


class SeverityTests(unittest.TestCase):
    def test_worst_of_an_empty_set_is_ok(self):
        self.assertEqual(Severity.worst([]), Severity.OK)

    def test_critical_beats_major(self):
        self.assertEqual(
            Severity.worst([Severity.MAJOR, Severity.CRITICAL, Severity.OK]),
            Severity.CRITICAL,
        )


if __name__ == "__main__":
    unittest.main()
