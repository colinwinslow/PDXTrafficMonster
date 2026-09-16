# Evidence: live collector v0.6 — run 2026-09-16T15:54:19Z on claude-box

Overall: **A PASS (live)**, **F PASS (live)**,
**H PASS in part (live: restart-persistence half; unit: exception half)**,
**B / C / D / E / G unit-tested, NOT LIVE-VERIFIED** (no API key exists, so no
keyed request has ever been made). Regenerate this file when a key lands.

**The anchor artifact does not exist yet.** `live-collector-bdd.md` defines it
as the first real `trimet/<day>/*_vehiclepositions.pb.gz`, which requires an
AppID. The static `gtfs.zip` below is a real captured artifact and satisfies
Scenario F, but it is not the anchor.

No paired spec (`docs/specs/live-collector.md`) yet: the collector was built
ahead of its spec because both keyed sources are live-only and every
uncollected day is lost (ADR-0003). Spec is retroactive (STATUS.md).

Supersedes the earlier evidence in git history. **Five** architecture review
rounds ran against this artifact; each returned CONCERNS and the findings were
fixed, hence v0.6. Round 6 is pending at the time of writing.

Two findings are worth carrying forward, because both are the same defect
shape — a fix applied to one place and not its siblings:

- **Round 4:** switching to `read1()` (a round-3 fix, to make the watchdog pet
  fire per recv) silently re-opened the truncation hole that the *other*
  round-3 fix had just closed, because `read1()` returns `b""` rather than
  raising on a short `Content-Length` body. A truncated 29.5 MB `gtfs.zip`
  would have been archived as a complete 200 with a sha256 over partial bytes.
- **Round 5:** the resulting truncation guard was added to the success branch
  but not the `HTTPError` branch, where `e.read()` on a short error body raises
  `IncompleteRead` *inside* an except block that the general handler does not
  cover. It escaped `fetch()` entirely: no manifest line, no backoff ladder,
  green heartbeat. Both now closed and pinned by real-socket tests.

Commands, verbatim, from repo root unless noted:

```
./scripts/install_collector.sh                    # runs the suite, installs to /usr/local/lib, restarts
python3 -W error::ResourceWarning -m unittest tests.test_collect_live
wc -l < /home/claude/data/pdxtrafficmonster/trimet_static/manifest.jsonl
python3 -c "import json,time; s=json.load(open('.../schedule.json')); now=time.time(); print({k: round((v-now)/3600,2) for k,v in s.items()})"
cat /home/claude/data/pdxtrafficmonster/status.json
find /home/claude/data/pdxtrafficmonster -mindepth 1 | sort
systemctl show pdxtrafficmonster-collector.service -p MainPID -p NRestarts -p WatchdogUSec
```

## Unit test run (raw tail)

```
Ran 39 tests in 0.238s

OK
```

### Positive controls — the tests fail against deliberately re-broken code

A passing test proves nothing unless it can fail. Each round-3 fix was
re-broken in a scratch copy (`/tmp/ctrl*`, deleted after) and the suite re-run:

```
--- control: read1->read, HTTPException dropped, schedule clamp dropped ---
FAIL: test_uses_read1_so_the_pet_fires_per_recv_not_per_body
FAIL: test_incomplete_read_is_caught_not_raised
FAIL: test_truncated_download_is_recorded_in_the_manifest
FAIL: test_future_epoch_is_clamped_to_the_sources_own_max_defer
Ran 4 tests — FAILED (failures=4)

--- control: save_schedule removed from _trimet only ---
FAIL: ... (source='trimet')
AssertionError: unexpectedly None : trimet fetched with no schedule.json at all

--- control: save_schedule removed from _tomtom_tiles only ---
FAIL: ... (source='tomtom_tiles')
AssertionError: 1700000000.0 not greater than 1700000000.0 : tomtom_tiles fetched before persisting its own deferred epoch

--- control: the r.length truncation check removed (round-4 finding 1) ---
FAIL: test_truncated_content_length_body_is_a_failure_not_a_200
AssertionError: Tuples differ: (200, 'application/zip', b'xxx...') != (0, 'IncompleteRead', b'')
FAIL: test_truncated_download_is_recorded_in_the_manifest_and_no_file_written
AssertionError: Tuples differ: (200, 100) != (0, 0)
   (100 delivered bytes of a declared 1000, reported as a successful capture)

--- control: load_schedule made a no-op (round-4 finding 2) ---
FAIL: test_a_stored_epoch_is_restored_as_the_exact_remaining_wait
FAIL: test_future_epoch_is_clamped_to_exactly_the_sources_max_defer
FAIL: test_past_epoch_makes_a_source_due_immediately

--- control: unguarded e.read() restored on the HTTPError branch (round-5 finding 1) ---
ERROR: test_truncated_error_body_still_yields_its_status_not_an_escape
ERROR: test_erroring_source_records_a_manifest_line_and_backs_off
http.client.IncompleteRead: IncompleteRead(50 bytes read, 4950 more expected)
   journal: "trimet_static: cycle error IncompleteRead ...; deferring 21600s"
   (i.e. escaped fetch(), no manifest line, no backoff ladder)

--- control: a handler caps backoff with a literal 4 instead of MAX_BACKOFF ---
FAIL: test_trimet_backoff_saturates_at_the_table_value
AssertionError: 4 != 16 : trimet ladder saturated at 4, not MAX_BACKOFF

--- brittleness check: behaviour-preserving refactor (cap = MAX_BACKOFF[...]; min(..., cap)) ---
Ran 4 tests — OK   (the ladder test pins behaviour, not source text)
```

The backoff test was itself rewritten this round: round 5 showed the original
grepped the source, which made it simultaneously tautological (it could not see
a wrong *value*) and brittle (a behaviour-preserving refactor failed it). It
now drives real failures until the ladder saturates.

**Two controls failed to fail, and each exposed a defect in the test rather
than in the code.** (1) `test_every_source_persists_its_schedule_before_fetching`
matched sources by substring, and `"trimet" in url` also matches
`developer.trimet.org/schedule/gtfs.zip` — so with `_trimet`'s save removed it
silently read the *static* handler's save and reported OK. Fixed with exact
per-source predicates plus an assertion on the persisted **value**. (2) The
first `TestSchedule` pair asserted only inequalities (`<= max_defer`,
`<= clock`), which a collector that ignored `schedule.json` entirely satisfies
vacuously, since `next_due` just stays `0.0`. Rewritten to assert exact waits.
All controls shown are from the corrected tests.

The truncation tests deliberately drive a **real socket** (`TrickleServer`: a
localhost server that declares `Content-Length: 1000` then sends 100 bytes),
because the earlier hand-written fake modelled `read1()` *raising* — a path
real `http.client` never takes for a `Content-Length` body. The fake tested a
branch that does not occur in production and passed while the code was broken.

## Scenario A — runs before any key exists: PASS (live)

All of the below is from the **current v0.6 process, PID 2172056**.

Given — env file absent. When — installed, started from `/usr/local/lib`:
```
Active: active (running) since Wed 2026-09-16 08:54:19 PDT
Main PID: 2172056 (python3)
2026-09-16T08:54:19-07:00 python3[2172056]: 2026-09-16T15:54:19+00:00 collector starting; env file /home/claude/.config/pdxtrafficmonster/env
```
Then — heartbeat (1 s old when sampled), keys false, TomTom gated, disk healthy:
```
$ date -u +%FT%TZ ; cat status.json
2026-09-16T15:55:10Z
{
 "heartbeat": "2026-09-16T15:55:09.997277+00:00",
 "env_error": null,
 "keys_present": {"TRIMET_APP_ID": false, "TOMTOM_API_KEY": false},
 "tomtom_enabled": false,
 "disk_free_bytes": 27758915584,
 "last_results": {},
 "next_due_in_s": {"trimet": 55, "trimet_static": 604062, "tomtom_tiles": 60, "tomtom_segments": 60}
}
```
`schedule.json` independently agrees with those due times (`trimet: 55s`,
`trimet_static: 604061s`, both tomtom `60s`), and the process is in
`hrtimer_nanosleep` — i.e. idling on its tick, not wedged.

Then — no keyed request: only `trimet_static/` exists; no `trimet/`,
`tomtom_tiles/`, `tomtom_segments/` directory has ever been created.
Then — watchdog fed (`WatchdogUSec=20min`, `NRestarts=0`); on the v0.3 build
the monotonic watchdog timestamp was observed advancing across a 12 s sample
(1013606937492 → 1013616941106).
Then — exactly **two** waiting lines on this boot, one per missing credential:
```
2026-09-16T08:55:04-07:00 python3[2172056]: trimet: no TRIMET_APP_ID in ...; waiting
2026-09-16T08:55:09-07:00 python3[2172056]: tomtom: no TOMTOM_API_KEY in ...; waiting
$ journalctl ... _PID=2172056 | grep -c waiting
2
```
Two, not three: `tomtom_tiles` and `tomtom_segments` share one gate warning for
the single missing TomTom key. Note they appear 45 s and 50 s after start, not
at startup — each source warns when it first comes *due*, and the schedule
restored from the previous boot deferred them. (This briefly looked like a
stall; it is not — the heartbeat above was 1 s old throughout.) The
one-per-hour throttle itself was measured on v0.1 (34 lines / 16.5 h uptime,
exact match to 2 × ceil(16.5)) and the `warn_hourly` path is unchanged since,
apart from its clock source.

## Scenario F — static GTFS without any key: PASS (live)

```
{"fetched_at": "2026-09-16T15:34:28.833445+00:00", ..., "status": 200, "bytes": 29521107,
 "sha256": "82e6b822de008367b3d3d35bb52545807ea41b6f56623a9aa4b1162b3d54671b",
 "path": "trimet_static/2026-09-16/153428Z_gtfs.zip"}
$ sha256sum trimet_static/2026-09-16/153428Z_gtfs.zip
82e6b822de008367b3d3d35bb52545807ea41b6f56623a9aa4b1162b3d54671b   <- matches manifest
$ python3 -c "...zipfile..."
True 20      <- testzip() clean, 20 entries
TriMet,...,20260823,20270227,20260823-20260910-0900,...
```
The `feed_version` is byte-identical to the `feed_info.txt` committed in
`docs/research/samples/trimet_gtfs/` on 2026-09-15 — an independent check that
this is the real feed.

Known one-time cost: two snapshots exist (15:34:28, 15:42:51), byte-identical
(same sha256, 59 MB total). The 15:42 refetch happened because the v0.3 restart
was the first start *after* schedule persistence was introduced, so no
`schedule.json` existed yet. Not recurring — see H below.

## Scenario H — a broken source can't stall/overspend others: PASS in part

**Restart half — live.** Across the v0.4 restart at 15:47:01, with
`schedule.json` present from the v0.3 run:
```
$ wc -l < trimet_static/manifest.jsonl
2                                  <- still 2; no third fetch on restart
$ ... hours until due
{'trimet': 0.01, 'trimet_static': 167.93, 'tomtom_tiles': 0.01, 'tomtom_segments': 0.01}
```
`trimet_static` correctly stayed ~168 h (7 days) out instead of refetching
29.5 MB. This is the round-2 refire-loop fix confirmed in production, not just
in a unit test.

**Exception half — unit.** `test_store_exception_in_tiles_charges_budget_reschedules_and_does_not_stop_others`
raises `OSError(ENOSPC)` from `store()` at the default zoom (20 tiles) and
asserts: budget charged the full 20, tiles deferred by `ERROR_DEFER`, exactly
one tile fetched, no refire next cycle, and TriMet + segments still ran.
`test_static_gtfs_exception_defers_hours_not_minutes` pins the 6 h static defer.

## Scenarios B, C, D, E, G — unit only, NOT LIVE-VERIFIED

- **B** (key picked up without restart): `load_config()` runs every cycle;
  `test_with_keys_and_enable_fetches_every_source_and_redacts`. Needs the real
  event: same `MainPID`, snapshot within one interval of writing the env file.
- **C** (daily caps): `test_spend_and_cap_persist_across_instances_and_reset_by_day`,
  `test_corrupt_budget_file_resets_instead_of_crashing`,
  `test_default_tile_budget_fits_monthly_quota_and_watchdog` (20 tiles × 288/day
  clamped to 5,500 → 170,500/31 d < 200K; 6 × 72 = 432/day → 13,392 < 20K; and
  `WatchdogSec` > every per-request `DEADLINE`). The cap-*skip* branch is still
  code-reading only.
- **D** (keys never leak): `redact` + `scrub` incl. percent-encoded forms
  (`test_scrub_removes_secret_values_including_percent_encoded_forms`); no
  manifest contains an injected `SECRET`. Not verified against a real journal.
- **E** (failures recorded): `test_store_records_failure_without_writing_file`;
  `test_failed_trimet_fetch_backs_off_and_recovers` (403 → backoff 2 → 200 →
  backoff 1; manifest statuses `[403, 200]`); and the truncation half is
  covered against a real socket by
  `test_truncated_download_is_recorded_in_the_manifest_and_no_file_written`
  (manifest line `status: 0, content_type: IncompleteRead, path: null,
  sha256: null`; no day directory created; static deferred 6 h). That last one
  is closer to live than unit — it exercises real `http.client` over a real TCP
  connection — but it still does not touch `developer.trimet.org`.
- **G** (TomTom gate): `test_tomtom_key_without_enable_flag_never_fetches_tomtom`;
  live `status.json` shows `tomtom_enabled: false` with no key present.

## Open gaps

- No keyed request has ever been made; B/C/D(journal)/E/G await a real key.
- Cap-skip branch and the `MIN_FREE_BYTES` guard are unit-tested with mocks,
  never exercised live.
- Hourly-warning cadence not re-measured since v0.1.
- 59 MB of byte-identical GTFS duplicates on disk (harmless, dedupable).
