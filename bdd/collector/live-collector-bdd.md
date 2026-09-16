# BDD: live collector (TriMet GTFS-RT + static GTFS)

Feature: capture live-only arterial data on claude-box from the moment a key
exists, as raw bytes with provenance, without ever exposing the key.

Anchor artifact: the first real `trimet/<day>/<HHMMSS>Z_vehiclepositions.pb.gz`
on disk with a matching `manifest.jsonl` line (sha256, redacted URL, HTTP 200).

## Scenario A — runs before any key exists
Given no `/home/claude/.config/pdxtrafficmonster/env`
When the service is started
Then it stays up (survives its systemd watchdog window), writes `status.json`
  with `keys_present` all false, makes no keyed request (only the keyless
  static-GTFS snapshot of Scenario F), and logs one "waiting" line per missing
  credential per hour — one, for the absent TriMet AppID. It appears when the
  source first comes *due* (which a restored schedule may defer past startup),
  not at the moment the process starts.

## Scenario B — a key added later is picked up without a restart
Given the service is running with no keys
When `TRIMET_APP_ID=...` is written to the env file
Then within one cycle (≤5 s) plus the source interval, a `.pb.gz` snapshot
  and a manifest line appear, and `status.json.keys_present.TRIMET_APP_ID` is true.

## Scenario D — keys never leak
Given keys are configured
When any request is made (success or failure)
Then neither the journal nor any `manifest.jsonl` contains the key value
  (URLs are stored with `appID`/`key` replaced by `REDACTED`).

## Scenario E — failures are recorded, not hidden
Given a source returns non-200 (e.g. 403 bad AppID, 429 rate limit)
When the fetch completes
Then a manifest line records the status with `path: null`, no file is written,
  and that source's next attempt is delayed while the others continue —
  by a ×2 backoff ladder (capped at MAX_BACKOFF) for `trimet`, and by a fixed
  multi-hour defer for `trimet_static`,
  which has no ladder because its normal interval is a week.
And given the error body arrives slowly rather than failing outright
Then the read is still bounded by that source's deadline and still feeds the
  watchdog, because a single blocking read would stall every other source too.
And given a response is TRUNCATED (declared `Content-Length` not delivered)
Then it is recorded as a failure — never stored as a successful capture with a
  sha256 over partial bytes, which would be fabricated provenance
  (`CLAUDE.md` invariant 1).

## Scenario F — static GTFS is snapshotted without any key
Given the service is running (keys or not)
When the first cycle runs, and then weekly
Then `trimet_static/<day>/<HHMMSS>Z_gtfs.zip` (uncompressed zip, ~30 MB) and a
  manifest line with sha256 exist, so any later bus speed can be traced to the
  `stops`/`trips`/`shapes` of the feed version that was live.

## Scenario H — one broken source cannot stall the other
Given a source's store() raises mid-cycle (disk full, read-only remount)
When the cycle completes
Then that source is deferred by its own ERROR_DEFER (no refire on the next 5 s
  tick) and the other source still runs in the same cycle.
And given the process is then killed and restarted (crash, watchdog, deploy)
Then the persisted schedule (`schedule.json`) is honoured, so the restart does
  not re-fetch either — a crash loop cannot become a re-download loop (the
  static GTFS is 29.5 MB a time).

## Evidence
`bdd/collector/live-collector-evidence.md` (written at first real capture).
Unit tests: `python3 -m unittest tests.test_collect_live`.
