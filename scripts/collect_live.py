#!/usr/bin/env python3
"""Live-data collector: TriMet GTFS-RT vehicle positions + the static GTFS they resolve against.

Stores every response as raw bytes with a manifest line, so the archive is provenance, not
interpretation. Stdlib only. Re-reads the env file every cycle so a key added later is picked
up without a restart. Each source is isolated: one failing source cannot stall another, and the
schedule survives restarts so a crash cannot turn into a refire loop.

TomTom was removed 2026-09-16 after reading its developer T&C — §11.4 prohibits storing Results,
which is the whole job of this program. See ADR-0001 and docs/research/samples/README.md §4.

Do not run `--once` while the service is running: schedule.json is a single-writer file.
"""
import gzip
import hashlib
import http.client
import json
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
USER_AGENT = "PDXTrafficMonster-collector/1.0 (+https://github.com/colinwinslow/PDXTrafficMonster)"
TRIMET_VP_URL = "https://developer.trimet.org/ws/V1/VehiclePositions"
TRIMET_GTFS_URL = "https://developer.trimet.org/schedule/gtfs.zip"
KEY_PARAMS = ("appID",)
SECRET_VARS = ("TRIMET_APP_ID",)
MIN_FREE_BYTES = 1 << 30
ERROR_BODY_LIMIT = 2000  # how much of an HTTP error body is worth keeping for diagnosis
TICK_SECONDS = 5
CHUNK = 1 << 20
SOURCES = ("trimet", "trimet_static")
# How long a source sleeps after an unexpected exception (not an HTTP error) before retrying.
ERROR_DEFER = {"trimet": 300, "trimet_static": 6 * 3600}
# Hard wall-clock ceilings per request; the watchdog is fed per chunk inside these.
DEADLINE = {"trimet": 60, "trimet_static": 900}
# Largest legitimate backoff multiplier per source. Single source of truth: the handlers cap
# their backoff with this AND load_schedule clamps a restored epoch with it. If these drift
# apart the clamp starts shortening legitimate defers.
MAX_BACKOFF = {"trimet": 16, "trimet_static": 1}
INTERVAL_VAR = {
    "trimet": "PDXTM_TRIMET_INTERVAL",
    "trimet_static": "PDXTM_TRIMET_STATIC_INTERVAL",
}

DEFAULTS = {
    "PDXTM_DATA_DIR": "/home/claude/data/pdxtrafficmonster",
    "PDXTM_TRIMET_INTERVAL": "30",
    "PDXTM_TRIMET_STATIC_INTERVAL": str(7 * 24 * 3600),
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


def snapshot_path(data_dir, source, name, ext, now, compress=True):
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%SZ")
    return os.path.join(data_dir, source, day, f"{stamp}_{name}.{ext}" + (".gz" if compress else ""))


def _read_guarded(r, deadline, pet, clock, start, limit=None):
    """Read a body in chunks, petting the watchdog per chunk and honouring `deadline`.

    Returns (body, flag) where flag is None, "deadline" or "limit". This is the ONLY body-reading
    loop in this module, used by both the success and the HTTP-error path: a slow or dribbling
    error body stalls every source just as effectively as a slow success body, because run_once
    is single-threaded. Keeping one loop is deliberate — two copies diverged within one review
    round the last time this was split.
    """
    chunks, total = [], 0
    read_chunk = getattr(r, "read1", None) or r.read
    while True:
        if deadline is not None and clock() - start > deadline:
            return b"".join(chunks), "deadline"
        c = read_chunk(CHUNK)
        if not c:
            return b"".join(chunks), None
        chunks.append(c)
        total += len(c)
        if pet:
            pet()
        if limit is not None and total >= limit:
            return b"".join(chunks)[:limit], "limit"


def fetch(url, timeout=20, deadline=None, pet=None, clock=time.monotonic):
    """GET url. Reads in chunks, feeding `pet()` per chunk; aborts past `deadline` seconds."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = clock()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, flag = _read_guarded(r, deadline, pet, clock, start)
            if flag == "deadline":
                return 0, "DeadlineExceeded", b""
            # read1() does NOT raise IncompleteRead for identity/Content-Length bodies: on a
            # premature peer close it just returns b"". Without this check a truncated download
            # is archived as a complete 200 with a sha256 over partial bytes — fabricated
            # provenance, which invariant 1 forbids. r.length is the undelivered remainder
            # (None for chunked, where IncompleteRead *is* raised and caught below).
            # Gap, accepted: r.length is also None for a close-delimited body (HTTP/1.0 or
            # Connection: close), where truncation is undetectable by construction. Every source
            # this collector fetches serves Content-Length or chunked — see ADR-0003 "Open".
            if getattr(r, "length", None):
                return 0, "IncompleteRead", b""
            return r.status, r.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as e:
        # The error body gets the SAME treatment as the success body, deliberately: it can raise
        # IncompleteRead (raising here escapes fetch(), losing the manifest line and the backoff
        # ladder), and it can dribble (a plain e.read() is one blocking whole-body read, so it
        # honours no deadline and pets the watchdog zero times — stalling every source until
        # SIGABRT). Either way the HTTP status is still reported, because that is the fact the
        # manifest needs.
        try:
            err_body, flag = _read_guarded(e, deadline, pet, clock, start, limit=ERROR_BODY_LIMIT)
        except (OSError, ValueError, http.client.HTTPException):
            err_body, flag = b"", None
        # Mark a clipped error body rather than letting the manifest imply the server sent exactly
        # ERROR_BODY_LIMIT bytes — a stored length that isn't the real length is a small synthesis.
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        if flag:
            ctype = f"{ctype} ({flag}-truncated)".strip()
        return e.code, ctype, err_body
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
        self.last_results_at = None
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
        # Accepts the legacy flat {source: epoch} layout as well as {"next_due": ..., "backoff": ...}.
        due = saved.get("next_due") if isinstance(saved.get("next_due"), dict) else saved
        saved_backoff = saved.get("backoff") if isinstance(saved.get("backoff"), dict) else {}
        for s in SOURCES:
            b = saved_backoff.get(s)
            if isinstance(b, int) and 1 <= b <= MAX_BACKOFF[s]:
                self.backoff[s] = b
        now_wall, now_mono = self.wall(), self.clock()
        for s in SOURCES:
            v = due.get(s)
            if isinstance(v, (int, float)):
                # Clamp: a stored epoch in the future (clock ahead during the previous run, a
                # restored snapshot, a start before NTP) must not park a source indefinitely —
                # that is a silent stall with a green heartbeat, the exact failure unattended
                # capture cannot afford.
                wait = min(max(0.0, v - now_wall), self.max_defer(s, cfg))
                self.next_due[s] = now_mono + wait

    def save_schedule(self, data_dir):
        now_wall, now_mono = self.wall(), self.clock()
        # The backoff ladder is persisted alongside next_due: restarting a saturated ladder at ×1
        # would hammer an endpoint that is already failing, which is what the ladder exists to stop.
        out = {"next_due": {s: now_wall + max(0.0, self.next_due[s] - now_mono) for s in SOURCES},
               "backoff": dict(self.backoff)}
        tmp = os.path.join(data_dir, "schedule.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, os.path.join(data_dir, "schedule.json"))

    def _fetch(self, source, url, timeout=20):
        r = fetch(url, timeout=timeout, deadline=DEADLINE[source], pet=self.pet, clock=self.clock)
        self.pet()
        return r

    # ---- sources -------------------------------------------------------------------------

    def _trimet(self, cfg, now):
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

    def _trimet_static(self, cfg, now):
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

    # ---- cycle ---------------------------------------------------------------------------

    def run_once(self, cfg, now):
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
        handlers = {"trimet": self._trimet, "trimet_static": self._trimet_static}
        for source, handler in handlers.items():
            if self.clock() < self.next_due[source]:
                continue
            try:
                r = handler(cfg, now)
                if r is not None:
                    results[source] = r
            except Exception as e:  # isolate: one broken source must not stall or free-retry the other
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
            "disk_free_bytes": free,
            # Stamped: last_results is sticky (it holds the last NON-empty cycle), so without a
            # timestamp a reader cannot tell a 2-second-old success from a 6-day-old one.
            "last_results": results,
            "last_results_at": self.last_results_at,
            "backoff": dict(self.backoff),
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
            r = self.run_once(cfg, now)
            if r:
                last_results = r
                self.last_results_at = now.isoformat()
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
        print(json.dumps(Collector().cycle({})))
    else:
        Collector().run()
