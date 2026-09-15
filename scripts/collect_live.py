#!/usr/bin/env python3
"""Live-data collector: TriMet GTFS-RT vehicle positions + TomTom traffic flow.

Stores every response as raw bytes (gzip) with a manifest line, so the archive
is provenance, not interpretation. Stdlib only. Re-reads the env file every
cycle so a key added later is picked up without a restart.
"""
import gzip
import hashlib
import json
import math
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ENV_FILE = os.environ.get("PDXTM_ENV_FILE", "/home/claude/.config/pdxtrafficmonster/env")
USER_AGENT = "PDXTrafficMonster-collector/0.1 (+https://github.com/colinwinslow/PDXTrafficMonster)"
TRIMET_VP_URL = "https://developer.trimet.org/ws/V1/VehiclePositions"
TOMTOM_TILE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/{style}/{z}/{x}/{y}.pbf"
TOMTOM_SEG_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"
KEY_PARAMS = ("appID", "key")

DEFAULTS = {
    "PDXTM_DATA_DIR": "/home/claude/data/pdxtrafficmonster",
    "PDXTM_TRIMET_INTERVAL": "30",
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
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("PDXTM_") or k in ("TRIMET_APP_ID", "TOMTOM_API_KEY")})
    try:
        with open(ENV_FILE) as f:
            cfg.update(parse_env(f.read()))
    except FileNotFoundError:
        pass
    return cfg


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


def snapshot_path(data_dir, source, name, ext, now):
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%SZ")
    return os.path.join(data_dir, source, day, f"{stamp}_{name}.{ext}.gz")


class BudgetGuard:
    """Per-source, per-UTC-day request counter persisted to disk."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path) as f:
                self.state = json.load(f)
        except (FileNotFoundError, ValueError):
            self.state = {}

    def _key(self, source, now):
        return f"{source}:{now.strftime('%Y-%m-%d')}"

    def remaining(self, source, cap, now):
        return cap - self.state.get(self._key(source, now), 0)

    def spend(self, source, n, now):
        k = self._key(source, now)
        self.state[k] = self.state.get(k, 0) + n
        keep = {k2: v for k2, v in self.state.items() if k2.endswith(now.strftime("%Y-%m-%d"))}
        self.state = keep
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", e.read()[:2000]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e), b""


def store(data_dir, source, name, ext, url, status, ctype, body, now):
    path = snapshot_path(data_dir, source, name, ext, now)
    os.makedirs(os.path.join(data_dir, source), exist_ok=True)
    ok = status == 200 and len(body) > 0
    if ok:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with gzip.open(path, "wb") as f:
            f.write(body)
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


class Collector:
    def __init__(self):
        self.stop = False
        self.next_due = {"trimet": 0.0, "tomtom_tiles": 0.0, "tomtom_segments": 0.0}
        self.backoff = {"trimet": 1, "tomtom_tiles": 1, "tomtom_segments": 1}
        self.last_warn = {}
        signal.signal(signal.SIGTERM, self._sig)
        signal.signal(signal.SIGINT, self._sig)

    def _sig(self, *_):
        self.stop = True

    def warn_hourly(self, key, msg):
        t = time.time()
        if t - self.last_warn.get(key, 0) > 3600:
            self.last_warn[key] = t
            log(msg)

    def run_once(self, cfg, budget, now):
        data_dir = cfg["PDXTM_DATA_DIR"]
        t = time.time()
        results = {}

        if t >= self.next_due["trimet"]:
            interval = float(cfg["PDXTM_TRIMET_INTERVAL"])
            app_id = cfg.get("TRIMET_APP_ID", "")
            if not app_id:
                self.warn_hourly("trimet", f"trimet: no TRIMET_APP_ID in {ENV_FILE}; waiting")
                self.next_due["trimet"] = t + 60
            else:
                url = TRIMET_VP_URL + "?" + urllib.parse.urlencode({"appID": app_id})
                status, ctype, body = fetch(url)
                ok, _ = store(data_dir, "trimet", "vehiclepositions", "pb", url, status, ctype, body, now)
                results["trimet"] = (status, len(body))
                self.backoff["trimet"] = 1 if ok else min(self.backoff["trimet"] * 2, 16)
                self.next_due["trimet"] = t + interval * self.backoff["trimet"]

        tomtom_key = cfg.get("TOMTOM_API_KEY", "")

        if t >= self.next_due["tomtom_tiles"]:
            interval = float(cfg["PDXTM_TOMTOM_TILE_INTERVAL"])
            if not tomtom_key:
                self.warn_hourly("tomtom", f"tomtom: no TOMTOM_API_KEY in {ENV_FILE}; waiting")
                self.next_due["tomtom_tiles"] = t + 60
            else:
                z = int(cfg["PDXTM_TOMTOM_TILE_ZOOM"])
                tiles = tile_range(cfg["PDXTM_TOMTOM_BBOX"], z)
                styles = [s.strip() for s in cfg["PDXTM_TOMTOM_TILE_STYLES"].split(",") if s.strip()]
                need = len(tiles) * len(styles)
                cap = int(cfg["PDXTM_TOMTOM_TILE_DAILY_CAP"])
                if budget.remaining("tomtom_tiles", cap, now) < need:
                    self.warn_hourly("tiles_cap", f"tomtom_tiles: daily cap {cap} reached; skipping until tomorrow")
                    self.next_due["tomtom_tiles"] = t + 600
                else:
                    n_ok = 0
                    for style in styles:
                        for x, y in tiles:
                            url = TOMTOM_TILE_URL.format(style=style, z=z, x=x, y=y) + "?" + urllib.parse.urlencode({"key": tomtom_key})
                            status, ctype, body = fetch(url)
                            ok, _ = store(data_dir, "tomtom_tiles", f"{style}_z{z}_{x}_{y}", "pbf", url, status, ctype, body, now)
                            n_ok += ok
                            if status == 429:
                                break
                    budget.spend("tomtom_tiles", need, now)
                    results["tomtom_tiles"] = (n_ok, need)
                    self.backoff["tomtom_tiles"] = 1 if n_ok == need else min(self.backoff["tomtom_tiles"] * 2, 8)
                    self.next_due["tomtom_tiles"] = t + interval * self.backoff["tomtom_tiles"]

        if t >= self.next_due["tomtom_segments"]:
            interval = float(cfg["PDXTM_TOMTOM_SEGMENT_INTERVAL"])
            points = parse_points(cfg["PDXTM_TOMTOM_POINTS"])
            if not tomtom_key or not points:
                if tomtom_key and not points:
                    self.warn_hourly("points", "tomtom_segments: PDXTM_TOMTOM_POINTS empty; skipping")
                self.next_due["tomtom_segments"] = t + 60
            else:
                cap = int(cfg["PDXTM_TOMTOM_SEGMENT_DAILY_CAP"])
                if budget.remaining("tomtom_segments", cap, now) < len(points):
                    self.warn_hourly("seg_cap", f"tomtom_segments: daily cap {cap} reached; skipping until tomorrow")
                    self.next_due["tomtom_segments"] = t + 600
                else:
                    n_ok = 0
                    for i, (lat, lon) in enumerate(points):
                        url = TOMTOM_SEG_URL.format(zoom=cfg["PDXTM_TOMTOM_SEGMENT_ZOOM"]) + "?" + urllib.parse.urlencode(
                            {"key": tomtom_key, "point": f"{lat},{lon}", "unit": "MPH"})
                        status, ctype, body = fetch(url)
                        ok, _ = store(data_dir, "tomtom_segments", f"p{i:02d}_{lat}_{lon}", "json", url, status, ctype, body, now)
                        n_ok += ok
                        if status == 429:
                            break
                    budget.spend("tomtom_segments", len(points), now)
                    results["tomtom_segments"] = (n_ok, len(points))
                    self.backoff["tomtom_segments"] = 1 if n_ok == len(points) else min(self.backoff["tomtom_segments"] * 2, 8)
                    self.next_due["tomtom_segments"] = t + interval * self.backoff["tomtom_segments"]

        return results

    def write_status(self, cfg, results, now):
        data_dir = cfg["PDXTM_DATA_DIR"]
        os.makedirs(data_dir, exist_ok=True)
        status = {
            "heartbeat": now.isoformat(),
            "env_file": ENV_FILE,
            "keys_present": {"TRIMET_APP_ID": bool(cfg.get("TRIMET_APP_ID")), "TOMTOM_API_KEY": bool(cfg.get("TOMTOM_API_KEY"))},
            "last_results": results,
            "next_due_in_s": {k: round(max(0.0, v - time.time())) for k, v in self.next_due.items()},
        }
        tmp = os.path.join(data_dir, "status.json.tmp")
        with open(tmp, "w") as f:
            json.dump(status, f, indent=1)
        os.replace(tmp, os.path.join(data_dir, "status.json"))

    def run(self):
        log(f"collector starting; env file {ENV_FILE}")
        last_results = {}
        while not self.stop:
            cfg = load_config()
            now = datetime.now(timezone.utc)
            os.makedirs(cfg["PDXTM_DATA_DIR"], exist_ok=True)
            budget = BudgetGuard(os.path.join(cfg["PDXTM_DATA_DIR"], "budget.json"))
            try:
                r = self.run_once(cfg, budget, now)
                if r:
                    last_results = r
                    log("fetched " + json.dumps(r))
            except Exception as e:  # keep the daemon alive; the manifest has the per-request truth
                log(f"cycle error: {type(e).__name__}: {e}")
            self.write_status(cfg, last_results, now)
            for _ in range(5):
                if self.stop:
                    break
                time.sleep(1)
        log("collector stopped")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        cfg = load_config()
        now = datetime.now(timezone.utc)
        os.makedirs(cfg["PDXTM_DATA_DIR"], exist_ok=True)
        c = Collector()
        print(json.dumps(c.run_once(cfg, BudgetGuard(os.path.join(cfg["PDXTM_DATA_DIR"], "budget.json")), now)))
    else:
        Collector().run()
