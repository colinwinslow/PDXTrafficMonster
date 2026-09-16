import gzip
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import collect_live as cl  # noqa: E402

NOW = datetime(2026, 9, 15, 1, 2, 3, tzinfo=timezone.utc)
KEYED = dict(TRIMET_APP_ID="TSECRET123", TOMTOM_API_KEY="KSECRET123", PDXTM_TOMTOM_ENABLED="1",
             PDXTM_TOMTOM_POINTS="45.53,-122.66")


def read(path):
    with open(path) as f:
        return f.read()


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def fake_fetch(calls, status=200):
    def _f(url, timeout=20, deadline=None, pet=None, clock=None):
        calls.append(url)
        if pet:
            pet()
        return status, "application/octet-stream", b"payload"
    return _f


def make(clock=None, pets=None):
    return cl.Collector(clock=clock or FakeClock(), pet=(lambda: pets.append(1)) if pets is not None else (lambda: None),
                        wall=lambda: 1_700_000_000.0)


class TestPureHelpers(unittest.TestCase):
    def test_parse_env_handles_comments_quotes_and_blank(self):
        text = "# comment\n\nTRIMET_APP_ID='abc123'\nTOMTOM_API_KEY=\"k\"\nPDXTM_X = 5 \nBAD LINE\n"
        self.assertEqual(cl.parse_env(text), {"TRIMET_APP_ID": "abc123", "TOMTOM_API_KEY": "k", "PDXTM_X": "5"})

    def test_redact_strips_both_key_params_and_keeps_others(self):
        r = cl.redact("https://x/y?appID=SECRET1&point=1,2&key=SECRET2")
        self.assertNotIn("SECRET", r)
        self.assertIn("point=1%2C2", r)
        self.assertIn("appID=REDACTED", r)
        self.assertIn("key=REDACTED", r)

    def test_scrub_removes_secret_values_including_percent_encoded_forms(self):
        secrets = cl.secrets_of({"TRIMET_APP_ID": "TS+CRET/123", "TOMTOM_API_KEY": "short"})
        self.assertIn("TS+CRET/123", secrets)
        self.assertIn(urllib.parse.quote("TS+CRET/123", safe=""), secrets)
        self.assertIn(urllib.parse.quote_plus("TS+CRET/123"), secrets)
        msg = "ValueError: unknown url type: 'x?appID=" + urllib.parse.quote_plus("TS+CRET/123") + "' raw TS+CRET/123"
        self.assertEqual(cl.scrub(msg, secrets), "ValueError: unknown url type: 'x?appID=REDACTED' raw REDACTED")

    def test_tile_contains_its_point(self):
        import math
        lon, lat, z = -122.6668, 45.5316, 14
        x, y = cl.lonlat_to_tile(lon, lat, z)
        n = 2 ** z
        west, east = x / n * 360.0 - 180.0, (x + 1) / n * 360.0 - 180.0
        north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        self.assertTrue(west <= lon < east)
        self.assertTrue(south <= lat < north)
        self.assertEqual((x, y), (2609, 5859))  # hand-derived: (57.3332/360)*16384 = 2609.3

    def test_default_tile_budget_fits_monthly_quota_and_watchdog(self):
        tiles = cl.tile_range(cl.DEFAULTS["PDXTM_TOMTOM_BBOX"], int(cl.DEFAULTS["PDXTM_TOMTOM_TILE_ZOOM"]))
        self.assertEqual(len(tiles), 20)
        per_day = min(len(tiles) * (86400 // int(cl.DEFAULTS["PDXTM_TOMTOM_TILE_INTERVAL"])),
                      int(cl.DEFAULTS["PDXTM_TOMTOM_TILE_DAILY_CAP"]))
        self.assertLess(per_day * 31, 200_000)
        pts = len(cl.parse_points(cl.DEFAULTS["PDXTM_TOMTOM_POINTS"]))
        seg_per_day = min(pts * (86400 // int(cl.DEFAULTS["PDXTM_TOMTOM_SEGMENT_INTERVAL"])),
                          int(cl.DEFAULTS["PDXTM_TOMTOM_SEGMENT_DAILY_CAP"]))
        self.assertLess(seg_per_day * 31, 20_000)
        # The watchdog is fed per fetch, so the window only needs to exceed ONE request's ceiling.
        unit = read(os.path.join(os.path.dirname(__file__), "..", "scripts", "systemd", "pdxtrafficmonster-collector.service"))
        watchdog = int([l for l in unit.splitlines() if l.startswith("WatchdogSec=")][0].split("=")[1])
        self.assertGreater(watchdog, max(cl.DEADLINE.values()))

    def test_parse_points(self):
        self.assertEqual(cl.parse_points("45.5,-122.6; 45.6,-122.7;"), [(45.5, -122.6), (45.6, -122.7)])
        self.assertEqual(cl.parse_points(""), [])

    def test_snapshot_path_is_utc_day_partitioned(self):
        now = datetime(2026, 9, 15, 23, 59, 40, tzinfo=timezone.utc)
        self.assertEqual(cl.snapshot_path("/d", "trimet", "vehiclepositions", "pb", now),
                         "/d/trimet/2026-09-15/235940Z_vehiclepositions.pb.gz")
        self.assertEqual(cl.snapshot_path("/d", "trimet_static", "gtfs", "zip", now, compress=False),
                         "/d/trimet_static/2026-09-15/235940Z_gtfs.zip")


class Resp:
    """Models http.client.HTTPResponse: read(n) blocks for n bytes, read1(n) returns what's ready."""
    status = 200
    headers = {"Content-Type": "application/zip"}

    def __init__(self, body, per_recv=3, raise_incomplete=False):
        self.buf = body
        self.per_recv = per_recv
        self.raise_incomplete = raise_incomplete

    def read(self, n=None):
        out, self.buf = self.buf, b""
        return out

    def read1(self, n):
        if self.raise_incomplete and self.buf:
            raise cl.http.client.IncompleteRead(b"partial", 999)
        take = min(n, self.per_recv, len(self.buf))
        out, self.buf = self.buf[:take], self.buf[take:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.orig = cl.urllib.request.urlopen

    def tearDown(self):
        cl.urllib.request.urlopen = self.orig

    def test_uses_read1_so_the_pet_fires_per_recv_not_per_body(self):
        # read() would hand back all 12 bytes in one call (one pet); read1 yields 3 at a time.
        cl.urllib.request.urlopen = lambda req, timeout=20: Resp(b"x" * 12, per_recv=3)
        pets = []
        st, ct, body = cl.fetch("https://x", pet=lambda: pets.append(1))
        self.assertEqual((st, body), (200, b"x" * 12))
        self.assertEqual(len(pets), 4, "expected one pet per recv-sized chunk, not one per body")

    def test_deadline_aborts_without_storing_a_partial_body(self):
        clock = FakeClock()

        def ticking():
            clock.t += 100
            return clock.t
        cl.urllib.request.urlopen = lambda req, timeout=20: Resp(b"x" * 12, per_recv=3)
        st, ct, body = cl.fetch("https://x", deadline=150, clock=ticking)
        self.assertEqual((st, ct, body), (0, "DeadlineExceeded", b""))

    def test_raised_incomplete_read_is_caught_chunked_case(self):
        # For a CHUNKED body http.client does raise IncompleteRead. It is an HTTPException, not an
        # OSError, so it needs its own except clause or it escapes fetch and never reaches the
        # manifest. (The Content-Length case does NOT raise — see TestRealSocketTruncation.)
        self.assertFalse(issubclass(cl.http.client.IncompleteRead, (OSError, ValueError)))
        cl.urllib.request.urlopen = lambda req, timeout=20: Resp(b"x" * 12, raise_incomplete=True)
        st, ct, body = cl.fetch("https://x")
        self.assertEqual((st, ct, body), (0, "IncompleteRead", b""))


class TrickleServer:
    """A real HTTP server that declares Content-Length and then sends fewer bytes."""

    def __init__(self, declared, actual, chunk=None, status=b"200 OK", delay=0.0):
        self.declared, self.actual, self.chunk, self.status, self.delay = declared, actual, chunk, status, delay
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.t = threading.Thread(target=self._serve, daemon=True)
        self.t.start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                conn.recv(65536)
                conn.sendall(b"HTTP/1.1 " + self.status + b"\r\nContent-Type: application/zip\r\n"
                             b"Content-Length: %d\r\n\r\n" % self.declared)
                body = b"x" * self.actual
                step = self.chunk or len(body) or 1
                for i in range(0, len(body), step):
                    conn.sendall(body[i:i + step])
                    if self.delay:
                        time.sleep(self.delay)
        except OSError:
            pass

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def close(self):
        self.sock.close()


class TestRealSocketTruncation(unittest.TestCase):
    """read1() does NOT raise IncompleteRead on a Content-Length body — it returns b"".
    These go through real http.client, because a hand-written fake response cannot show that."""

    def test_truncated_content_length_body_is_a_failure_not_a_200(self):
        srv = TrickleServer(declared=1000, actual=100)
        self.addCleanup(srv.close)
        st, ct, body = cl.fetch(srv.url)
        self.assertEqual((st, ct, body), (0, "IncompleteRead", b""),
                         "a short body must never be reported as a successful capture")

    def test_complete_body_still_succeeds(self):  # positive control for the test above
        srv = TrickleServer(declared=100, actual=100)
        self.addCleanup(srv.close)
        st, ct, body = cl.fetch(srv.url)
        self.assertEqual((st, len(body)), (200, 100))
        self.assertEqual(ct, "application/zip")

    def test_multi_chunk_body_pets_more_than_once(self):
        srv = TrickleServer(declared=40000, actual=40000, chunk=8192)
        self.addCleanup(srv.close)
        pets = []
        st, _, body = cl.fetch(srv.url, pet=lambda: pets.append(1))
        self.assertEqual((st, len(body)), (200, 40000))
        self.assertGreater(len(pets), 1, "read1 should yield several recv-sized chunks")

    def test_truncated_error_body_still_yields_its_status_not_an_escape(self):
        # e.read() on a short error body raises IncompleteRead INSIDE the except HTTPError block,
        # which is not covered by the general handler. If it escapes fetch(), the source loses
        # both its manifest line and its backoff ladder while the process looks healthy.
        srv = TrickleServer(declared=5000, actual=50, status=b"503 Service Unavailable")
        self.addCleanup(srv.close)
        st, ct, body = cl.fetch(srv.url)
        self.assertEqual(st, 503, "a truncated error body must still report its HTTP status")

    def test_dribbling_error_body_honours_the_deadline_and_pets_the_watchdog(self):
        # A plain e.read() is one blocking whole-body read: it would return only after the whole
        # 5 kB dribbled in (~50 s), honouring no deadline and petting zero times, stalling every
        # source until SIGABRT. The error body must get the same guarded read as a success body.
        # The deadline must bind BEFORE ERROR_BODY_LIMIT does, or this asserts nothing: reaching
        # the 2000-byte cap here takes ~2.0s, so a 0.5s deadline is the only thing that can end
        # the read early. (Round 7 added the cap and silently hollowed out this exact test.)
        srv = TrickleServer(declared=5000, actual=5000, chunk=50, status=b"503 Service Unavailable", delay=0.05)
        self.addCleanup(srv.close)
        pets = []
        t0 = time.monotonic()
        st, _, body = cl.fetch(srv.url, deadline=0.5, pet=lambda: pets.append(1))
        elapsed = time.monotonic() - t0
        self.assertEqual(st, 503, "the HTTP status must still reach the manifest")
        self.assertLess(len(body), cl.ERROR_BODY_LIMIT,
                        "the cap, not the deadline, ended this read — the test would prove nothing")
        self.assertLess(elapsed, 1.5, f"deadline not honoured on the error body ({elapsed:.1f}s)")
        self.assertGreater(len(pets), 0, "watchdog never petted while reading the error body")

    def test_erroring_static_source_records_a_manifest_line_and_defers_for_hours(self):
        srv = TrickleServer(declared=5000, actual=50, status=b"403 Forbidden")
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as d:
            # Short interval on purpose: with the 7-day default, an assertion that the source is
            # deferred >= ERROR_DEFER passes even when the error defer is deleted entirely.
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, PDXTM_TRIMET_STATIC_INTERVAL="60")
            orig = cl.TRIMET_GTFS_URL
            cl.TRIMET_GTFS_URL = srv.url
            try:
                c = make()
                r = c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            finally:
                cl.TRIMET_GTFS_URL = orig
            self.assertEqual(r["trimet_static"][0], 403)
            entry = json.loads(read(os.path.join(d, "trimet_static", "manifest.jsonl")).splitlines()[0])
            self.assertEqual((entry["status"], entry["path"]), (403, None))
            wait = c.next_due["trimet_static"] - c.clock()
            self.assertAlmostEqual(wait, cl.ERROR_DEFER["trimet_static"], delta=1,
                                   msg="a failed static fetch must retry in hours, not sit on its interval")

    def test_truncated_download_is_recorded_in_the_manifest_and_no_file_written(self):
        srv = TrickleServer(declared=1000, actual=100)
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            orig = cl.TRIMET_GTFS_URL
            cl.TRIMET_GTFS_URL = srv.url
            try:
                c = make()
                r = c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            finally:
                cl.TRIMET_GTFS_URL = orig
            self.assertEqual(r["trimet_static"], (0, 0))
            entry = json.loads(read(os.path.join(d, "trimet_static", "manifest.jsonl")).splitlines()[0])
            self.assertEqual((entry["status"], entry["content_type"], entry["path"], entry["sha256"]),
                             (0, "IncompleteRead", None, None))
            self.assertFalse(os.path.exists(os.path.join(d, "trimet_static", "2026-09-15")))
            self.assertGreaterEqual(c.next_due["trimet_static"] - c.clock(), cl.ERROR_DEFER["trimet_static"])


class TestReadGuarded(unittest.TestCase):
    """One body-reading loop, used by both paths. Two copies diverged inside a single review
    round the last time this was split, so these pin that it is actually shared."""

    def test_fetch_has_exactly_one_body_reading_loop(self):
        src = read(os.path.join(os.path.dirname(__file__), "..", "scripts", "collect_live.py"))
        fetch_src = src[src.index("def fetch("):src.index("def store(")]
        self.assertEqual(fetch_src.count("_read_guarded("), 2,
                         "both the success and the error path must call the shared helper")
        self.assertNotIn("read1(CHUNK)", fetch_src,
                         "fetch() should not re-implement the chunked read inline")

    def test_error_body_is_capped_and_the_cap_is_marked(self):
        srv = TrickleServer(declared=9000, actual=9000, chunk=1000, status=b"503 Service Unavailable")
        self.addCleanup(srv.close)
        st, ct, body = cl.fetch(srv.url)
        self.assertEqual(st, 503)
        self.assertEqual(len(body), cl.ERROR_BODY_LIMIT, "error bodies must be capped")
        self.assertIn("truncated", ct,
                      "a clipped body must say so, or the manifest implies the server sent exactly the cap")

    def test_short_error_body_is_not_marked_truncated(self):  # control for the above
        srv = TrickleServer(declared=10, actual=10, status=b"403 Forbidden")
        self.addCleanup(srv.close)
        st, ct, body = cl.fetch(srv.url)
        self.assertEqual((st, len(body)), (403, 10))
        self.assertNotIn("truncated", ct)


class TestSchedule(unittest.TestCase):
    WALL = 1_700_000_000.0

    def _loaded(self, d, epochs, cfg):
        with open(os.path.join(d, "schedule.json"), "w") as f:
            json.dump(epochs, f)
        c = cl.Collector(clock=FakeClock(), pet=lambda: None, wall=lambda: self.WALL)
        c.load_schedule(cfg)
        return c

    def test_a_stored_epoch_is_restored_as_the_exact_remaining_wait(self):
        # Asserts the VALUE. An earlier version asserted only `<= max_defer`, which a collector
        # that ignored schedule.json entirely satisfied vacuously (next_due stays 0.0).
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            c = self._loaded(d, {s: self.WALL + 137 for s in cl.SOURCES}, cfg)
            for s in cl.SOURCES:
                self.assertAlmostEqual(c.next_due[s] - c.clock(), 137, delta=0.01,
                                       msg=f"{s} did not restore its persisted wait")

    def test_future_epoch_is_clamped_to_exactly_the_sources_max_defer(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            c = self._loaded(d, {s: self.WALL + 365 * 86400 for s in cl.SOURCES}, cfg)
            for s in cl.SOURCES:
                self.assertAlmostEqual(c.next_due[s] - c.clock(), c.max_defer(s, cfg), delta=0.01,
                                       msg=f"{s} was not clamped to its max legitimate wait")

    def test_past_epoch_makes_a_source_due_immediately(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            c = self._loaded(d, {s: self.WALL - 99999 for s in cl.SOURCES}, cfg)
            for s in cl.SOURCES:
                self.assertAlmostEqual(c.next_due[s] - c.clock(), 0.0, delta=0.01)

    def test_clamp_never_shortens_a_legitimate_maximal_defer(self):
        # If max_defer < interval * MAX_BACKOFF, load_schedule would pull a correctly-backed-off
        # source forward on restart — the clamp turning into a spend amplifier.
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            c = cl.Collector(clock=FakeClock(), pet=lambda: None, wall=lambda: self.WALL)
            for s in cl.SOURCES:
                interval = float(cfg[cl.INTERVAL_VAR[s]])
                self.assertGreaterEqual(c.max_defer(s, cfg) + 0.01, interval * cl.MAX_BACKOFF[s],
                                        f"{s}: clamp is tighter than its own maximal backoff")


class TestBackoffLadder(unittest.TestCase):
    """Behavioural, not a source grep: drive real failures until the ladder saturates."""

    def setUp(self):
        self.orig_fetch = cl.fetch

    def tearDown(self):
        cl.fetch = self.orig_fetch

    def _saturate(self, cfg, source, cycles=12):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cfg, PDXTM_DATA_DIR=d)
            clock = FakeClock()
            c = cl.Collector(clock=clock, pet=lambda: None, wall=lambda: 1_700_000_000.0)
            budget = cl.BudgetGuard(os.path.join(d, "budget.json"))
            cl.fetch = fake_fetch([], status=500)
            seen = []
            for _ in range(cycles):
                c.run_once(cfg, budget, NOW)
                seen.append(c.backoff[source])
                clock.t += 10_000_000  # always due again
            return seen

    def test_trimet_backoff_saturates_at_the_table_value(self):
        seen = self._saturate(dict(cl.DEFAULTS, TRIMET_APP_ID="TSECRET123",
                                   PDXTM_TRIMET_STATIC_INTERVAL="999999999"), "trimet")
        self.assertEqual(max(seen), cl.MAX_BACKOFF["trimet"],
                         f"trimet ladder saturated at {max(seen)}, not MAX_BACKOFF")
        self.assertTrue(all(b <= cl.MAX_BACKOFF["trimet"] for b in seen))
        self.assertGreater(len(set(seen)), 1, "backoff never climbed at all")

    def test_tomtom_tiles_backoff_saturates_at_the_table_value(self):
        cfg = dict(cl.DEFAULTS, **KEYED, PDXTM_TRIMET_STATIC_INTERVAL="999999999",
                   PDXTM_TOMTOM_TILE_ZOOM="12", PDXTM_TOMTOM_TILE_DAILY_CAP="100000")
        seen = self._saturate(cfg, "tomtom_tiles")
        self.assertEqual(max(seen), cl.MAX_BACKOFF["tomtom_tiles"])

    def test_tomtom_segments_backoff_saturates_at_the_table_value(self):
        cfg = dict(cl.DEFAULTS, **KEYED, PDXTM_TRIMET_STATIC_INTERVAL="999999999",
                   PDXTM_TOMTOM_SEGMENT_DAILY_CAP="100000")
        seen = self._saturate(cfg, "tomtom_segments")
        self.assertEqual(max(seen), cl.MAX_BACKOFF["tomtom_segments"])

    # Exact, mutually exclusive predicates. A substring like "trimet" also matches
    # developer.trimet.org/schedule/gtfs.zip, which made an earlier version of this test read the
    # STATIC handler's save and pass while _trimet saved nothing.
    URL_IS = {
        "trimet": lambda u: "VehiclePositions" in u,
        "trimet_static": lambda u: u == cl.TRIMET_GTFS_URL,
        "tomtom_tiles": lambda u: "tile/flow" in u,
        "tomtom_segments": lambda u: "flowSegmentData" in u,
    }

    def test_every_source_persists_its_schedule_before_fetching(self):
        # The round-2 fix landed on the tomtom handlers only; this pins all four.
        wall = 1_700_000_000.0
        for source, extra in (("trimet", dict(TRIMET_APP_ID="TSECRET123")),
                              ("trimet_static", {}),
                              ("tomtom_tiles", KEYED),
                              ("tomtom_segments", KEYED)):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as d:
                cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **extra)
                seen = {}
                orig_fetch = cl.fetch

                def spy(url, timeout=20, deadline=None, pet=None, clock=None, _s=source, _d=d):
                    if self.URL_IS[_s](url) and _s not in seen:
                        try:
                            with open(os.path.join(_d, "schedule.json")) as f:
                                seen[_s] = json.load(f)["next_due"].get(_s)
                        except (FileNotFoundError, ValueError, KeyError):
                            seen[_s] = None
                    return 200, "application/octet-stream", b"payload"
                cl.fetch = spy
                try:
                    cl.Collector(clock=FakeClock(), pet=lambda: None, wall=lambda: wall).run_once(
                        cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
                finally:
                    cl.fetch = orig_fetch
                # Its own deferred epoch must already be on disk — not merely a file some EARLIER
                # source wrote this cycle, which would still carry this source's stale epoch.
                self.assertIsNotNone(seen.get(source), f"{source} fetched with no schedule.json at all")
                self.assertGreater(seen[source], wall,
                                   f"{source} fetched before persisting its own deferred epoch")


class TestConfig(unittest.TestCase):
    def test_unreadable_env_file_is_reported_not_raised(self):
        if os.geteuid() == 0:
            self.skipTest("root can read anything")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "env")
            with open(p, "w") as f:
                f.write("TRIMET_APP_ID=x\n")
            os.chmod(p, 0)
            old = cl.ENV_FILE
            cl.ENV_FILE = p
            try:
                cfg, err = cl.load_config()
            finally:
                cl.ENV_FILE = old
                os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
            self.assertIn("PermissionError", err)
            self.assertFalse(cfg.get("TRIMET_APP_ID"))


class TestBudgetGuard(unittest.TestCase):
    def test_spend_and_cap_persist_across_instances_and_reset_by_day(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "budget.json")
            day1 = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
            g = cl.BudgetGuard(path)
            self.assertEqual(g.remaining("tomtom_tiles", 10, day1), 10)
            g.spend("tomtom_tiles", 7, day1)
            self.assertEqual(cl.BudgetGuard(path).remaining("tomtom_tiles", 10, day1), 3)
            day2 = datetime(2026, 9, 16, 0, 1, tzinfo=timezone.utc)
            self.assertEqual(cl.BudgetGuard(path).remaining("tomtom_tiles", 10, day2), 10)

    def test_corrupt_schedule_file_does_not_crash(self):
        # Sibling of the budget test below — it existed for budget.json but not schedule.json.
        # Note the honest limit: a corrupt schedule silently zeroes every next_due, so the next
        # cycle re-pulls the 29.5 MB gtfs.zip. Only reachable via external corruption, since
        # save_schedule writes tmp+os.replace.
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            path = os.path.join(d, "schedule.json")
            for bad in ('{"next_due": null}', '{"backoff": "x"}', '{"next_due": {"trimet": "soon"}}',
                        '[1,2]', 'not json', '{"next_due": {"trimet": 1.7e9}, "backoff": {"trimet": 99}}'):
                with open(path, "w") as f:
                    f.write(bad)
                c = cl.Collector(clock=FakeClock(), pet=lambda: None, wall=lambda: 1_700_000_000.0)
                c.load_schedule(cfg)  # must not raise
                for s in cl.SOURCES:
                    self.assertTrue(1 <= c.backoff[s] <= cl.MAX_BACKOFF[s],
                                    f"{bad}: {s} restored an out-of-range backoff {c.backoff[s]}")

    def test_corrupt_budget_file_resets_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "budget.json")
            for bad in ("[1,2]", "not json", '{"tomtom_tiles:2026-09-15": "seven"}'):
                with open(path, "w") as f:
                    f.write(bad)
                self.assertEqual(cl.BudgetGuard(path).remaining("tomtom_tiles", 10, NOW), 10)


class TestStore(unittest.TestCase):
    def test_store_writes_gzip_and_manifest_without_key(self):
        with tempfile.TemporaryDirectory() as d:
            ok, entry = cl.store(d, "tomtom_segments", "p00", "json", "https://api.example/x?key=SECRET&point=1,2",
                                 200, "application/json", b'{"a":1}', NOW)
            self.assertTrue(ok)
            with gzip.open(os.path.join(d, entry["path"]), "rb") as f:
                self.assertEqual(f.read(), b'{"a":1}')
            text = read(os.path.join(d, "tomtom_segments", "manifest.jsonl"))
            self.assertEqual(json.loads(text.splitlines()[0])["sha256"], entry["sha256"])
            self.assertNotIn("SECRET", text)

    def test_store_uncompressed_zip(self):
        with tempfile.TemporaryDirectory() as d:
            ok, entry = cl.store(d, "trimet_static", "gtfs", "zip", cl.TRIMET_GTFS_URL, 200, "application/zip",
                                 b"PK\x03\x04", NOW, compress=False)
            self.assertTrue(ok)
            self.assertTrue(entry["path"].endswith("_gtfs.zip"))
            with open(os.path.join(d, entry["path"]), "rb") as f:
                self.assertEqual(f.read(), b"PK\x03\x04")

    def test_store_records_failure_without_writing_file(self):
        with tempfile.TemporaryDirectory() as d:
            ok, entry = cl.store(d, "trimet", "vehiclepositions", "pb", "https://x?appID=S", 403, "text/html", b"denied", NOW)
            self.assertFalse(ok)
            self.assertIsNone(entry["path"])
            self.assertFalse(os.path.exists(os.path.join(d, "trimet", "2026-09-15")))


class TestCycle(unittest.TestCase):
    def setUp(self):
        self.orig_fetch, self.orig_store = cl.fetch, cl.store

    def tearDown(self):
        cl.fetch, cl.store = self.orig_fetch, self.orig_store

    def test_without_keys_only_static_gtfs_is_fetched(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            calls = []
            cl.fetch = fake_fetch(calls)
            c = make()
            r = c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            c.write_status(cfg, r, NOW)
            self.assertEqual(calls, [cl.TRIMET_GTFS_URL])
            self.assertEqual(set(r), {"trimet_static"})
            with open(os.path.join(d, "status.json")) as f:
                st = json.load(f)
            self.assertEqual(st["keys_present"], {"TRIMET_APP_ID": False, "TOMTOM_API_KEY": False})
            self.assertFalse(st["tomtom_enabled"])
            r2 = c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertEqual(len(calls), 1)  # weekly: no immediate refetch
            self.assertEqual(r2, {})

    def test_a_429_abandons_every_style_not_just_the_current_one(self):
        # The break exited only the inner tile loop, so a second style still fired requests
        # after the rate limit. Its segments sibling has one loop, so it was already correct.
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED, PDXTM_TRIMET_STATIC_INTERVAL="999999999",
                       PDXTM_TOMTOM_TILE_ZOOM="12", PDXTM_TOMTOM_TILE_STYLES="absolute,relative")
            calls = []

            def rate_limited(url, timeout=20, deadline=None, pet=None, clock=None):
                calls.append(url)
                return (429, "text/plain", b"slow down") if "tile/flow" in url else (200, "", b"payload")
            cl.fetch = rate_limited
            make().run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertEqual(sum("tile/flow" in u for u in calls), 1,
                             "a 429 must stop the whole tile cycle, across styles")

    def test_tomtom_key_without_enable_flag_never_fetches_tomtom(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, TOMTOM_API_KEY="KSECRET123")
            calls = []
            cl.fetch = fake_fetch(calls)
            make().run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertFalse(any("tomtom" in u for u in calls))

    def test_with_keys_and_enable_fetches_every_source_and_redacts(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED)
            calls = []
            cl.fetch = fake_fetch(calls)
            pets = []
            r = make(pets=pets).run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertEqual(set(r), set(cl.SOURCES))
            self.assertTrue(any("appID=TSECRET123" in u for u in calls))
            self.assertEqual(sum("tile/flow" in u for u in calls), 20)  # default zoom, default bbox
            self.assertGreaterEqual(len(pets), 2 * len(calls))  # fed inside fetch and after each fetch
            for src in cl.SOURCES:
                self.assertNotIn("SECRET", read(os.path.join(d, src, "manifest.jsonl")))

    def test_store_exception_in_tiles_charges_budget_reschedules_and_does_not_stop_others(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED)
            calls = []
            cl.fetch = fake_fetch(calls)

            def failing_store(data_dir, source, *a, **k):
                if source == "tomtom_tiles":
                    raise OSError(28, "No space left on device")
                return self.orig_store(data_dir, source, *a, **k)
            cl.store = failing_store
            c = make()
            budget = cl.BudgetGuard(os.path.join(d, "budget.json"))
            r = c.run_once(cfg, budget, NOW)
            self.assertNotIn("tomtom_tiles", r)
            self.assertIn("tomtom_segments", r)
            self.assertIn("trimet", r)
            self.assertEqual(budget.remaining("tomtom_tiles", 10_000, NOW), 10_000 - 20)  # charged despite failure
            self.assertAlmostEqual(c.next_due["tomtom_tiles"] - c.clock(), cl.ERROR_DEFER["tomtom_tiles"], delta=0.01)
            n = sum("tile/flow" in u for u in calls)
            self.assertEqual(n, 1)  # raised on the first store, so exactly one tile was fetched
            c.run_once(cfg, budget, NOW)
            self.assertEqual(sum("tile/flow" in u for u in calls), n)  # nothing refired next tick

    def test_static_gtfs_exception_defers_hours_not_minutes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d)
            cl.fetch = fake_fetch([])

            def failing_store(data_dir, source, *a, **k):
                raise OSError(30, "Read-only file system")
            cl.store = failing_store
            c = make()
            c.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertGreaterEqual(c.next_due["trimet_static"] - c.clock(), 6 * 3600)

    def test_schedule_persists_across_restart_so_no_refire(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED)
            calls = []
            cl.fetch = fake_fetch(calls)
            c1 = make()
            r = c1.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            c1.write_status(cfg, r, NOW)
            self.assertTrue(os.path.exists(os.path.join(d, "schedule.json")))
            n = len(calls)
            c2 = make()  # "restart": fresh instance, same data dir, same wall clock
            r2 = c2.run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertEqual(len(calls), n)
            self.assertEqual(r2, {})
            self.assertGreater(c2.next_due["tomtom_tiles"] - c2.clock(), 250)

    def test_segments_charge_the_budget_before_fetching_too(self):
        # Sibling of the tiles test above: that one covered tiles only, so deleting the segments
        # budget.spend passed the whole suite.
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED, PDXTM_TRIMET_STATIC_INTERVAL="999999999")
            cl.fetch = fake_fetch([])

            def failing_store(data_dir, source, *a, **k):
                if source == "tomtom_segments":
                    raise OSError(28, "No space left on device")
                return self.orig_store(data_dir, source, *a, **k)
            cl.store = failing_store
            c = make()
            budget = cl.BudgetGuard(os.path.join(d, "budget.json"))
            r = c.run_once(cfg, budget, NOW)
            self.assertNotIn("tomtom_segments", r)
            npoints = len(cl.parse_points(cfg["PDXTM_TOMTOM_POINTS"]))
            self.assertEqual(budget.remaining("tomtom_segments", 10_000, NOW), 10_000 - npoints,
                             "segments must charge before fetching, like tiles")
            self.assertAlmostEqual(c.next_due["tomtom_segments"] - c.clock(),
                                   cl.ERROR_DEFER["tomtom_segments"], delta=0.01)

    def test_backoff_ladder_survives_a_restart(self):
        # next_due was persisted from round 2; the ladder was not. Restarting a saturated ladder
        # at x1 hammers an endpoint that is already failing.
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, TRIMET_APP_ID="TSECRET123",
                       PDXTM_TRIMET_STATIC_INTERVAL="999999999")
            clock = FakeClock()
            c1 = cl.Collector(clock=clock, pet=lambda: None, wall=lambda: 1_700_000_000.0)
            budget = cl.BudgetGuard(os.path.join(d, "budget.json"))
            cl.fetch = fake_fetch([], status=500)
            for _ in range(4):
                c1.run_once(cfg, budget, NOW)
                clock.t += 10_000
            c1.save_schedule(d)
            self.assertGreater(c1.backoff["trimet"], 1)
            c2 = cl.Collector(clock=FakeClock(), pet=lambda: None, wall=lambda: 1_700_000_000.0)
            c2.load_schedule(cfg)
            self.assertEqual(c2.backoff["trimet"], c1.backoff["trimet"],
                             "the backoff ladder must survive a restart, like next_due does")

    def test_status_stamps_when_last_results_was_captured(self):
        with tempfile.TemporaryDirectory() as d:
            cl.fetch = fake_fetch([])
            c = make()
            os.environ["PDXTM_DATA_DIR"] = d  # cycle() calls load_config() itself
            try:
                c.cycle({})
            finally:
                del os.environ["PDXTM_DATA_DIR"]
            with open(os.path.join(d, "status.json")) as f:
                st = json.load(f)
            self.assertTrue(st["last_results"])
            self.assertIsNotNone(st["last_results_at"], "a sticky last_results needs a timestamp")
            self.assertIn("backoff", st)

    def test_bad_config_value_isolated_to_its_source(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, **KEYED, PDXTM_TOMTOM_TILE_DAILY_CAP="lots")
            cl.fetch = fake_fetch([])
            r = make().run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            self.assertNotIn("tomtom_tiles", r)
            self.assertIn("tomtom_segments", r)
            self.assertIn("trimet", r)

    def test_disk_guard_blocks_all_fetches(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, TRIMET_APP_ID="TSECRET123")
            calls = []
            cl.fetch = fake_fetch(calls)
            orig = cl.shutil.disk_usage
            cl.shutil.disk_usage = lambda p: type("U", (), {"free": 10})()
            try:
                r = make().run_once(cfg, cl.BudgetGuard(os.path.join(d, "budget.json")), NOW)
            finally:
                cl.shutil.disk_usage = orig
            self.assertEqual(calls, [])
            self.assertEqual(r, {})

    def test_failed_trimet_fetch_backs_off_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(cl.DEFAULTS, PDXTM_DATA_DIR=d, TRIMET_APP_ID="TSECRET123", PDXTM_TRIMET_STATIC_INTERVAL="999999")
            clock = FakeClock()
            c = make(clock=clock)
            budget = cl.BudgetGuard(os.path.join(d, "budget.json"))
            cl.fetch = fake_fetch([], status=403)
            c.run_once(cfg, budget, NOW)
            self.assertEqual(c.backoff["trimet"], 2)
            self.assertAlmostEqual(c.next_due["trimet"] - clock(), 60, delta=0.01)
            clock.t += 61
            cl.fetch = fake_fetch([], status=200)
            c.run_once(cfg, budget, NOW)
            self.assertEqual(c.backoff["trimet"], 1)
            text = read(os.path.join(d, "trimet", "manifest.jsonl"))
            self.assertEqual([json.loads(l)["status"] for l in text.splitlines()], [403, 200])


if __name__ == "__main__":
    unittest.main()
