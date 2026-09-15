import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import collect_live as cl  # noqa: E402


class TestPureHelpers(unittest.TestCase):
    def test_parse_env_handles_comments_quotes_and_blank(self):
        text = "# comment\n\nTRIMET_APP_ID='abc123'\nTOMTOM_API_KEY=\"k\"\nPDXTM_X = 5 \nBAD LINE\n"
        self.assertEqual(cl.parse_env(text), {"TRIMET_APP_ID": "abc123", "TOMTOM_API_KEY": "k", "PDXTM_X": "5"})

    def test_redact_strips_both_key_params_and_keeps_others(self):
        u = "https://x/y?appID=SECRET1&point=1,2&key=SECRET2"
        r = cl.redact(u)
        self.assertNotIn("SECRET", r)
        self.assertIn("point=1%2C2", r)
        self.assertIn("appID=REDACTED", r)
        self.assertIn("key=REDACTED", r)

    def test_tile_contains_its_point(self):
        # Independent check via the inverse slippy formula: the tile's bounds must contain the point.
        import math
        lon, lat, z = -122.6668, 45.5316, 14
        x, y = cl.lonlat_to_tile(lon, lat, z)
        n = 2 ** z
        west = x / n * 360.0 - 180.0
        east = (x + 1) / n * 360.0 - 180.0
        north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        self.assertTrue(west <= lon < east, (west, lon, east))
        self.assertTrue(south <= lat < north, (south, lat, north))
        self.assertEqual((x, y), (2609, 5859))  # hand-derived: (57.3332/360)*16384 = 2609.3

    def test_tile_range_covers_bbox_and_is_small(self):
        tiles = cl.tile_range("45.52,-122.70,45.58,-122.64", 14)
        self.assertGreaterEqual(len(tiles), 4)
        self.assertLessEqual(len(tiles), 20)
        self.assertIn(cl.lonlat_to_tile(-122.6668, 45.5316, 14), tiles)

    def test_parse_points(self):
        self.assertEqual(cl.parse_points("45.5,-122.6; 45.6,-122.7;"), [(45.5, -122.6), (45.6, -122.7)])
        self.assertEqual(cl.parse_points(""), [])

    def test_snapshot_path_is_utc_day_partitioned(self):
        now = datetime(2026, 9, 15, 23, 59, 40, tzinfo=timezone.utc)
        p = cl.snapshot_path("/d", "trimet", "vehiclepositions", "pb", now)
        self.assertEqual(p, "/d/trimet/2026-09-15/235940Z_vehiclepositions.pb.gz")


class TestBudgetGuard(unittest.TestCase):
    def test_spend_and_cap_persist_across_instances_and_reset_by_day(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "budget.json")
            day1 = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
            g = cl.BudgetGuard(path)
            self.assertEqual(g.remaining("tomtom_tiles", 10, day1), 10)
            g.spend("tomtom_tiles", 7, day1)
            g2 = cl.BudgetGuard(path)
            self.assertEqual(g2.remaining("tomtom_tiles", 10, day1), 3)
            day2 = datetime(2026, 9, 16, 0, 1, tzinfo=timezone.utc)
            self.assertEqual(g2.remaining("tomtom_tiles", 10, day2), 10)


class TestStore(unittest.TestCase):
    def test_store_writes_gzip_and_manifest_without_key(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime(2026, 9, 15, 1, 2, 3, tzinfo=timezone.utc)
            url = "https://api.example/x?key=SECRET&point=1,2"
            ok, entry = cl.store(d, "tomtom_segments", "p00", "json", url, 200, "application/json", b'{"a":1}', now)
            self.assertTrue(ok)
            self.assertNotIn("SECRET", json.dumps(entry))
            import gzip
            with gzip.open(os.path.join(d, entry["path"]), "rb") as f:
                self.assertEqual(f.read(), b'{"a":1}')
            with open(os.path.join(d, "tomtom_segments", "manifest.jsonl")) as f:
                line = json.loads(f.readline())
            self.assertEqual(line["sha256"], entry["sha256"])
            self.assertNotIn("SECRET", open(os.path.join(d, "tomtom_segments", "manifest.jsonl")).read())

    def test_store_records_failure_without_writing_file(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime(2026, 9, 15, 1, 2, 3, tzinfo=timezone.utc)
            ok, entry = cl.store(d, "trimet", "vehiclepositions", "pb", "https://x?appID=S", 403, "text/html", b"denied", now)
            self.assertFalse(ok)
            self.assertIsNone(entry["path"])
            self.assertFalse(os.path.exists(os.path.join(d, "trimet", "2026-09-15")))


class TestNoKeyCycle(unittest.TestCase):
    def test_run_once_without_keys_makes_no_requests_and_writes_status(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS)
            cfg["PDXTM_DATA_DIR"] = d
            calls = []
            orig = cl.fetch
            cl.fetch = lambda url, timeout=20: calls.append(url) or (200, "", b"x")
            try:
                c = cl.Collector()
                now = datetime.now(timezone.utc)
                r = c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), now)
                c.write_status(cfg, r, now)
            finally:
                cl.fetch = orig
            self.assertEqual(calls, [])
            self.assertEqual(r, {})
            st = json.load(open(os.path.join(d, "status.json")))
            self.assertEqual(st["keys_present"], {"TRIMET_APP_ID": False, "TOMTOM_API_KEY": False})

    def test_run_once_with_keys_fetches_each_source_and_redacts(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS)
            cfg.update({"PDXTM_DATA_DIR": d, "TRIMET_APP_ID": "TSECRET", "TOMTOM_API_KEY": "KSECRET",
                        "PDXTM_TOMTOM_POINTS": "45.53,-122.66", "PDXTM_TOMTOM_TILE_ZOOM": "12"})
            calls = []
            orig = cl.fetch
            cl.fetch = lambda url, timeout=20: calls.append(url) or (200, "application/octet-stream", b"payload")
            try:
                r = cl.Collector().run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), datetime.now(timezone.utc))
            finally:
                cl.fetch = orig
            self.assertEqual(set(r), {"trimet", "tomtom_tiles", "tomtom_segments"})
            self.assertTrue(any("appID=TSECRET" in u for u in calls))
            for src in ("trimet", "tomtom_tiles", "tomtom_segments"):
                text = open(os.path.join(d, src, "manifest.jsonl")).read()
                self.assertNotIn("SECRET", text)


if __name__ == "__main__":
    unittest.main()
