#!/usr/bin/env python3
"""Live-data collector: TriMet GTFS-RT vehicle positions + static GTFS, TomTom traffic flow.

Stores every response as raw bytes with a manifest line, so the archive is
provenance, not interpretation. Stdlib only. Re-reads the env file every
cycle so a key added later is picked up without a restart. Each source is
isolated: one failing source cannot stall or overspend another, and the
schedule survives restarts so a crash cannot turn into a refire loop.

Do not run `--once` while the service is running: budget.json and
schedule.json are single-writer files.
"""
import gzip
import hashlib
import http.client
import json
import math
import os
import shutil
import signal
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ENV_FILE = os.environ.get("PDXTM_ENV_FILE", "/home/claude/.config/pdxtrafficmonster/env")
USER_AGENT = "PDXTrafficMonster-collector/0.5 (+https://github.com/colinwinslow/PDXTrafficMonster)"
TRIMET_VP_URL = "https://developer.trimet.org/ws/V1/VehiclePositions"
TRIMET_GTFS_URL = "https://developer.trimet.org/schedule/gtfs.zip"
TOMTOM_TILE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/{style}/{z}/{x}/{y}.pbf"
TOMTOM_SEG_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"
KEY_PARAMS = ("appID", "key")
SECRET_VARS = ("TRIMET_APP_ID", "TOMTOM_API_KEY")
MIN_FREE_BYTES = 1 << 30
TICK_SECONDS = 5
CHUNK = 1 << 20
SOURCES = ("trimet", "trimet_static", "tomtom_tiles", "tomtom_segments")
# How long a source sleeps after an unexpected exception (not an HTTP error) before retrying.
ERROR_DEFER = {"trimet": 300, "trimet_static": 6 * 3600, "tomtom_tiles": 300, "tomtom_segments": 1200}
# Hard wall-clock ceilings per request; the watchdog is fed per chunk inside these.
DEADLINE = {"trimet": 60, "trimet_static": 900, "tomtom_tiles": 60, "tomtom_segments": 60}
# Largest legitimate backoff multiplier per source. Single source of truth: the handlers cap
# their backoff with this AND load_schedule clamps a restored epoch with it. If these drift
# apart the clamp starts shortening legitimate defers, i.e. it becomes a spend amplifier.
MAX_BACKOFF = {"trimet": 16, "trimet_static": 1, "tomtom_tiles": 8, "tomtom_segments": 8}
INTERVAL_VAR = {
    "trimet": "PDXTM_TRIMET_INTERVAL",
    "trimet_static": "PDXTM_TRIMET_STATIC_INTERVAL",
    "tomtom_tiles": "PDXTM_TOMTOM_TILE_INTERVAL",
    "tomtom_segments": "PDXTM_TOMTOM_SEGMENT_INTERVAL",
}

DEFAULTS = {
    "PDXTM_DATA_DIR": "/home/claude/data/pdxtrafficmonster",
    "PDXTM_TRIMET_INTERVAL": "30",
    "PDXTM_TRIMET_STATIC_INTERVAL": str(7 * 24 * 3600),
    # TomTom stays off until the developer T&C on storing/redistributing responses has been
    # read (ADR-0001 "Open", ADR-0003); flip to 1 in the env file to enable.
    "PDXTM_TOMTOM_ENABLED": "0",
    "PDXTM_TOMTOM_TILE_INTERVAL": "300",
    "PDXTM_TOMTOM_TILE_ZOOM": "14",
    "PDXTM_TOMTOM_TILE_STYLES": "absolute",
    "PDXTM_TOMTOM_BBOX": "45.52,-122.70,45.58,-122.64",
    "PDXTM_TOMTOM_TILE_DAILY_CAP": "5500",
    "PDXTM_TOMTOM_SEGMENT_INTERVAL": "1200",
    "PDXTM_TOMTOM_SEGMENT_ZOOM": "12",
    # MLK@Broadway, MLK@Fremont, Interstate@Russell, Interstate@Going (OSM way midpoints),
    # then PORTAL stations 3121 (SB I-5 @ Broadway) and 3169 (NB) as loop-vs-probe cross-checks.
    "PDXTM_TOMTOM_POINTS": "45.535178,-122.66166;45.548648,-122.66152;45.540596,-122.67705;45.552799,-122.680888;"
                           "45.53675,-122.668429;45.536814,-122.66827",
    "PDXTM_TOMTOM_SEGMENT_DAILY_CAP": "600",
}


def parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load_config():
    """Returns (cfg, env_error). An unreadable env file is a warning, never a crash."""
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("PDXTM_") or k in SECRET_VARS})
    err = None
    try:
        with open(ENV_FILE) as f:
            cfg.update(parse_env(f.read()))
    except FileNotFoundError:
        pass
    except OSError as e:
        err = f"{type(e).__name__}: {e}"
    return cfg, err


def secrets_of(cfg):
    """Every textual form a secret could take in a URL or an exception message."""
    out = []
    for k in SECRET_VARS:
        v = cfg.get(k)
        if v and len(v) >= 6:
            for form in (v, urllib.parse.quote(v, safe=""), urllib.parse.quote_plus(v)):
                if form not in out:
                    out.append(form)
    return out


def scrub(text, secrets):
    for s in secrets:
        text = text.replace(s, "REDACTED")
    return text


def redact(url):
    parts = urllib.parse.urlsplit(url)
    q = [(k, "REDACTED" if k in KEY_PARAMS else v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_range(bbox, z):
    """bbox = 'south,west,north,east' -> sorted list of (x, y) tiles covering it."""
    s, w, n, e = (float(v) for v in bbox.split(","))
    x0, y0 = lonlat_to_tile(w, n, z)
    x1, y1 = lonlat_to_tile(e, s, z)
    return [(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]


def parse_points(text):
    pts = []
    for item in text.split(";"):
        item = item.strip()
        if not item:
            continue
        lat, lon = (float(v) for v in item.split(","))
        pts.append((lat, lon))
    return pts


def snapshot_path(data_dir, source, name, ext, now, compress=True):
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%SZ")
    return os.path.join(data_dir, source, day, f"{stamp}_{name}.{ext}" + (".gz" if compress else ""))


class BudgetGuard:
    """Per-source, per-UTC-day request counter persisted to disk."""

    def __init__(self, path):
        self.path = path
        self.state = {}
        try:
            with open(path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.state = {k: v for k, v in loaded.items() if isinstance(v, int)}
        except (FileNotFoundError, ValueError, OSError):
            pass

    def _key(self, source, now):
        return f"{source}:{now.strftime('%Y-%m-%d')}"

    def remaining(self, source, cap, now):
        return cap - self.state.get(self._key(source, now), 0)

    def spend(self, source, n, now):
        k = self._key(source, now)
        self.state[k] = self.state.get(k, 0) + n
        self.state = {k2: v for k2, v in self.state.items() if k2.endswith(now.strftime("%Y-%m-%d"))}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)


def fetch(url, timeout=20, deadline=None, pet=None, clock=time.monotonic):
    """GET url. Reads in chunks, feeding `pet()` per chunk; aborts past `deadline` seconds."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = clock()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            chunks = []
            while True:
                if deadline is not None and clock() - start > deadline:
                    return 0, "DeadlineExceeded", b""
                # read1, not read: read(n) blocks until n bytes or EOF, which would collapse a
                # small body to a single chunk and make the per-chunk pet/deadline inert.
                c = r.read1(CHUNK)
                if not c:
                    break
                chunks.append(c)
                if pet:
                    pet()
            # read1() does NOT raise IncompleteRead for identity/Content-Length bodies: on a
            # premature peer close it just returns b"". Without this check a truncated download
            # is archived as a complete 200 with a sha256 over partial bytes — fabricated
            # provenance, which invariant 1 forbids. r.length is the undelivered remainder
            # (None for chunked, where IncompleteRead *is* raised and caught below).
            if getattr(r, "length", None):
                return 0, "IncompleteRead", b""
            return r.status, r.headers.get("Content-Type", ""), b"".join(chunks)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", e.read()[:2000]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as e:
        # HTTPException covers IncompleteRead — a peer closing before Content-Length is satisfied,
        # the normal failure of a large download on a flaky link. It is NOT an OSError, and if it
        # escapes here the failure never reaches store() and so never reaches the manifest.
        return 0, f"{type(e).__name__}", b""


def store(data_dir, source, name, ext, url, status, ctype, body, now, compress=True):
    path = snapshot_path(data_dir, source, name, ext, now, compress)
    os.makedirs(os.path.join(data_dir, source), exist_ok=True)
    ok = status == 200 and len(body) > 0
    if ok:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        if compress:
            with gzip.open(tmp, "wb") as f:
                f.write(body)
        else:
            with open(tmp, "wb") as f:
                f.write(body)
        os.replace(tmp, path)
    entry = {
        "fetched_at": now.isoformat(),
        "source": source,
        "name": name,
        "url": redact(url),
        "status": status,
        "content_type": ctype,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest() if ok else None,
        "path": os.path.relpath(path, data_dir) if ok else None,
    }
    with open(os.path.join(data_dir, source, "manifest.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")
    return ok, entry


def log(msg):
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def sd_notify(state):
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(state.encode())
    except OSError:
        pass


class Collector:
    def __init__(self, clock=time.monotonic, pet=None, wall=time.time):
        self.stop = False
        self.clock = clock
        self.wall = wall
        self.pet = pet or (lambda: sd_notify("WATCHDOG=1"))
        self.next_due = {s: 0.0 for s in SOURCES}
        self.backoff = {s: 1 for s in SOURCES}
        self.last_warn = {}
        self.secrets = []
        self.schedule_loaded = False
        signal.signal(signal.SIGTERM, self._sig)
        signal.signal(signal.SIGINT, self._sig)

    def _sig(self, *_):
        self.stop = True

    def warn_hourly(self, key, msg):
        t = self.clock()
        if t - self.last_warn.get(key, -1e9) > 3600:
            self.last_warn[key] = t
            log(scrub(msg, self.secrets))

    def _defer(self, source, seconds):
        self.next_due[source] = self.clock() + seconds

    # ---- schedule persistence: a restart must not reset next_due (that is the refire loop) ----

    def max_defer(self, source, cfg):
        """The longest wait this source could legitimately have scheduled."""
        try:
            interval = float(cfg[INTERVAL_VAR[source]])
        except (KeyError, ValueError):
            interval = float(DEFAULTS[INTERVAL_VAR[source]])
        return max(interval * MAX_BACKOFF[source], ERROR_DEFER[source])

    def load_schedule(self, cfg):
        self.schedule_loaded = True
        try:
            with open(os.path.join(cfg["PDXTM_DATA_DIR"], "schedule.json")) as f:
                saved = json.load(f)
        except (FileNotFoundError, ValueError, OSError):
            return
        if not isinstance(saved, dict):
            return
        now_wall, now_mono = self.wall(), self.clock()
        for s in SOURCES:
            v = saved.get(s)
            if isinstance(v, (int, float)):
                # Clamp: a stored epoch in the future (clock ahead during the previous run, a
                # restored snapshot, a start before NTP) must not park a source indefinitely —
                # that is a silent stall with a green heartbeat, the exact failure unattended
                # capture cannot afford.
                wait = min(max(0.0, v - now_wall), self.max_defer(s, cfg))
                self.next_due[s] = now_mono + wait

    def save_schedule(self, data_dir):
        now_wall, now_mono = self.wall(), self.clock()
        out = {s: now_wall + max(0.0, self.next_due[s] - now_mono) for s in SOURCES}
        tmp = os.path.join(data_dir, "schedule.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, os.path.join(data_dir, "schedule.json"))

    def _fetch(self, source, url, timeout=20):
        r = fetch(url, timeout=timeout, deadline=DEADLINE[source], pet=self.pet, clock=self.clock)
        self.pet()
        return r

    # ---- sources -------------------------------------------------------------------------

    def _trimet(self, cfg, budget, now):
        interval = float(cfg["PDXTM_TRIMET_INTERVAL"])
        app_id = cfg.get("TRIMET_APP_ID", "")
        if not app_id:
            self.warn_hourly("trimet", f"trimet: no TRIMET_APP_ID in {ENV_FILE}; waiting")
            self._defer("trimet", 60)
            return None
        url = TRIMET_VP_URL + "?" + urllib.parse.urlencode({"appID": app_id})
        self._defer("trimet", interval * self.backoff["trimet"])
        self.save_schedule(cfg["PDXTM_DATA_DIR"])
        status, ctype, body = self._fetch("trimet", url)
        ok, _ = store(cfg["PDXTM_DATA_DIR"], "trimet", "vehiclepositions", "pb", url, status, ctype, body, now)
        self.backoff["trimet"] = 1 if ok else min(self.backoff["trimet"] * 2, MAX_BACKOFF["trimet"])
        self._defer("trimet", interval * self.backoff["trimet"])
        return (status, len(body))

    def _trimet_static(self, cfg, budget, now):
        interval = float(cfg["PDXTM_TRIMET_STATIC_INTERVAL"])
        self._defer("trimet_static", interval)
        # Persist before the fetch: a kill inside the (up to DEADLINE) download window must not
        # leave this still-due and re-pull 29.5 MB on every restart.
        self.save_schedule(cfg["PDXTM_DATA_DIR"])
        status, ctype, body = self._fetch("trimet_static", TRIMET_GTFS_URL, timeout=120)
        ok, _ = store(cfg["PDXTM_DATA_DIR"], "trimet_static", "gtfs", "zip", TRIMET_GTFS_URL, status, ctype, body, now, compress=False)
        if not ok:
            self._defer("trimet_static", ERROR_DEFER["trimet_static"])
        return (status, len(body))

    def _tomtom_gate(self, cfg):
        key = cfg.get("TOMTOM_API_KEY", "")
        if not key:
            self.warn_hourly("tomtom_key", f"tomtom: no TOMTOM_API_KEY in {ENV_FILE}; waiting")
            return None
        if cfg.get("PDXTM_TOMTOM_ENABLED", "0") != "1":
            self.warn_hourly("tomtom_gate", "tomtom: key present but PDXTM_TOMTOM_ENABLED != 1; "
                                            "read the developer T&C (ADR-0001 Open) then set it to 1")
            return None
        return key

    def _tomtom_tiles(self, cfg, budget, now):
        interval = float(cfg["PDXTM_TOMTOM_TILE_INTERVAL"])
        key = self._tomtom_gate(cfg)
        if not key:
            self._defer("tomtom_tiles", 60)
            return None
        z = int(cfg["PDXTM_TOMTOM_TILE_ZOOM"])
        tiles = tile_range(cfg["PDXTM_TOMTOM_BBOX"], z)
        styles = [s.strip() for s in cfg["PDXTM_TOMTOM_TILE_STYLES"].split(",") if s.strip()]
        need = len(tiles) * len(styles)
        cap = int(cfg["PDXTM_TOMTOM_TILE_DAILY_CAP"])
        if budget.remaining("tomtom_tiles", cap, now) < need:
            self.warn_hourly("tiles_cap", f"tomtom_tiles: daily cap {cap} reached; skipping until tomorrow (UTC)")
            self._defer("tomtom_tiles", 600)
            return None
        # Charge, reschedule, and persist BEFORE fetching: neither an exception mid-loop nor a
        # restart mid-loop may lead to a free retry.
        budget.spend("tomtom_tiles", need, now)
        self._defer("tomtom_tiles", interval * self.backoff["tomtom_tiles"])
        self.save_schedule(cfg["PDXTM_DATA_DIR"])
        n_ok = 0
        for style in styles:
            for x, y in tiles:
                url = TOMTOM_TILE_URL.format(style=style, z=z, x=x, y=y) + "?" + urllib.parse.urlencode({"key": key})
                status, ctype, body = self._fetch("tomtom_tiles", url)
                ok, _ = store(cfg["PDXTM_DATA_DIR"], "tomtom_tiles", f"{style}_z{z}_{x}_{y}", "pbf", url, status, ctype, body, now)
                n_ok += ok
                if status == 429:
                    break
        self.backoff["tomtom_tiles"] = 1 if n_ok == need else min(self.backoff["tomtom_tiles"] * 2, MAX_BACKOFF["tomtom_tiles"])
        self._defer("tomtom_tiles", interval * self.backoff["tomtom_tiles"])
        return (n_ok, need)

    def _tomtom_segments(self, cfg, budget, now):
        interval = float(cfg["PDXTM_TOMTOM_SEGMENT_INTERVAL"])
        key = self._tomtom_gate(cfg)
        points = parse_points(cfg["PDXTM_TOMTOM_POINTS"])
        if not key or not points:
            if key and not points:
                self.warn_hourly("points", "tomtom_segments: PDXTM_TOMTOM_POINTS empty; skipping")
            self._defer("tomtom_segments", 60)
            return None
        cap = int(cfg["PDXTM_TOMTOM_SEGMENT_DAILY_CAP"])
        if budget.remaining("tomtom_segments", cap, now) < len(points):
            self.warn_hourly("seg_cap", f"tomtom_segments: daily cap {cap} reached; skipping until tomorrow (UTC)")
            self._defer("tomtom_segments", 600)
            return None
        budget.spend("tomtom_segments", len(points), now)
        self._defer("tomtom_segments", interval * self.backoff["tomtom_segments"])
        self.save_schedule(cfg["PDXTM_DATA_DIR"])
        n_ok = 0
        for i, (lat, lon) in enumerate(points):
            url = TOMTOM_SEG_URL.format(zoom=cfg["PDXTM_TOMTOM_SEGMENT_ZOOM"]) + "?" + urllib.parse.urlencode(
                {"key": key, "point": f"{lat},{lon}", "unit": "MPH"})
            status, ctype, body = self._fetch("tomtom_segments", url)
            ok, _ = store(cfg["PDXTM_DATA_DIR"], "tomtom_segments", f"p{i:02d}_{lat}_{lon}", "json", url, status, ctype, body, now)
            n_ok += ok
            if status == 429:
                break
        self.backoff["tomtom_segments"] = 1 if n_ok == len(points) else min(self.backoff["tomtom_segments"] * 2, MAX_BACKOFF["tomtom_segments"])
        self._defer("tomtom_segments", interval * self.backoff["tomtom_segments"])
        return (n_ok, len(points))

    # ---- cycle ---------------------------------------------------------------------------

    def run_once(self, cfg, budget, now):
        self.secrets = secrets_of(cfg)
        data_dir = cfg["PDXTM_DATA_DIR"]
        if not self.schedule_loaded:
            self.load_schedule(cfg)
        results = {}
        try:
            free = shutil.disk_usage(data_dir).free
        except OSError:
            free = 0
        if free < MIN_FREE_BYTES:
            self.warn_hourly("disk", f"disk: {free} bytes free under {MIN_FREE_BYTES}; not fetching")
            return results
        handlers = {
            "trimet": self._trimet,
            "trimet_static": self._trimet_static,
            "tomtom_tiles": self._tomtom_tiles,
            "tomtom_segments": self._tomtom_segments,
        }
        for source, handler in handlers.items():
            if self.clock() < self.next_due[source]:
                continue
            try:
                r = handler(cfg, budget, now)
                if r is not None:
                    results[source] = r
            except Exception as e:  # isolate: one broken source must not stall or free-retry the others
                self._defer(source, ERROR_DEFER[source])
                log(scrub(f"{source}: cycle error {type(e).__name__}: {e}; deferring {ERROR_DEFER[source]}s", self.secrets))
        return results

    def write_status(self, cfg, results, now, env_error=None):
        data_dir = cfg["PDXTM_DATA_DIR"]
        os.makedirs(data_dir, exist_ok=True)
        try:
            free = shutil.disk_usage(data_dir).free
        except OSError:
            free = None
        status = {
            "heartbeat": now.isoformat(),
            "env_file": ENV_FILE,
            "env_error": env_error,
            "keys_present": {k: bool(cfg.get(k)) for k in SECRET_VARS},
            "tomtom_enabled": cfg.get("PDXTM_TOMTOM_ENABLED", "0") == "1",
            "disk_free_bytes": free,
            "last_results": results,
            "next_due_in_s": {k: round(max(0.0, v - self.clock())) for k, v in self.next_due.items()},
        }
        tmp = os.path.join(data_dir, "status.json.tmp")
        with open(tmp, "w") as f:
            json.dump(status, f, indent=1)
        os.replace(tmp, os.path.join(data_dir, "status.json"))

    def cycle(self, last_results):
        cfg, env_error = load_config()
        if env_error:
            self.warn_hourly("env", f"env: cannot read {ENV_FILE} ({env_error}); running with no keys")
        now = datetime.now(timezone.utc)
        try:
            os.makedirs(cfg["PDXTM_DATA_DIR"], exist_ok=True)
            budget = BudgetGuard(os.path.join(cfg["PDXTM_DATA_DIR"], "budget.json"))
            r = self.run_once(cfg, budget, now)
            if r:
                last_results = r
                log("fetched " + json.dumps(r))
        except Exception as e:
            log(scrub(f"cycle error: {type(e).__name__}: {e}", secrets_of(cfg)))
        try:
            self.write_status(cfg, last_results, now, env_error)
        except Exception as e:
            log(scrub(f"status write error: {type(e).__name__}: {e}", secrets_of(cfg)))
        try:
            self.save_schedule(cfg["PDXTM_DATA_DIR"])
        except Exception as e:  # separate from status: a stale schedule is its own failure mode
            log(scrub(f"schedule write error: {type(e).__name__}: {e}", secrets_of(cfg)))
        return last_results

    def run(self):
        log(f"collector starting; env file {ENV_FILE}")
        sd_notify("READY=1")
        last_results = {}
        while not self.stop:
            last_results = self.cycle(last_results)
            self.pet()
            for _ in range(TICK_SECONDS):
                if self.stop:
                    break
                time.sleep(1)
        log("collector stopped")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        c = Collector()
        print(json.dumps(c.cycle({})))
    else:
        Collector().run()
