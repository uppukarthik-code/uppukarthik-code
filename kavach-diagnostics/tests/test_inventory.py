import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kavach_diag.inventory import InventoryError, load_inventory, summarise

REGISTER = Path(__file__).resolve().parents[1] / "data/inventory/example_division_register.csv"

HEADER = "asset_id,type,stn_code,km,loco_no,shed\n"


def write(tmp: str, body: str, header: str = HEADER) -> str:
    path = Path(tmp) / "register.csv"
    path.write_text(header + body, encoding="utf-8")
    return str(path)


class InventoryTests(unittest.TestCase):
    def test_example_register_loads(self):
        assets = load_inventory(REGISTER)
        self.assertEqual(len(assets), 20)
        counts = summarise(assets)
        self.assertEqual(counts, {"SKU": 7, "TWR": 4, "RIU": 2, "LKU": 7})

    def test_column_aliases_are_accepted(self):
        with TemporaryDirectory() as tmp:
            path = write(tmp, "SKU-1,SKU,EXA,412/2,,\n")
            asset = load_inventory(path)[0]
        self.assertEqual(asset.station_code, "EXA")
        self.assertEqual(asset.km_post, "412/2")

    def test_loco_location_uses_shed_and_class(self):
        assets = load_inventory(REGISTER)
        loco = next(a for a in assets if a.asset_id == "LKU-30201")
        self.assertEqual(loco.location, "WAP-7 30201 (EXS)")
        self.assertEqual(loco.group, "EXS (locos)")

    def test_station_location_reads_as_an_engineer_would_write_it(self):
        assets = load_inventory(REGISTER)
        station = next(a for a in assets if a.asset_id == "SKU-EXA")
        self.assertEqual(station.location, "EXA - Example A Jn / KM 412/2 / UP-DN")

    def test_duplicate_asset_id_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = write(tmp, "SKU-1,SKU,EXA,1/0,,\nSKU-1,SKU,EXB,2/0,,\n")
            with self.assertRaises(InventoryError) as raised:
                load_inventory(path)
        self.assertIn("Duplicate asset_id", str(raised.exception))

    def test_unknown_asset_type_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = write(tmp, "X-1,GATEWAY,EXA,1/0,,\n")
            with self.assertRaises(InventoryError):
                load_inventory(path)

    def test_blank_rows_are_skipped(self):
        with TemporaryDirectory() as tmp:
            path = write(tmp, "SKU-1,SKU,EXA,1/0,,\n,,,,,\n")
            self.assertEqual(len(load_inventory(path)), 1)

    def test_missing_file_reports_clearly(self):
        with self.assertRaises(InventoryError):
            load_inventory("/nonexistent/register.csv")


if __name__ == "__main__":
    unittest.main()
