# BDD: live collector (TriMet GTFS-RT + TomTom flow)

Feature: capture live-only arterial data on claude-box from the moment keys
exist, as raw bytes with provenance, without ever exposing a key.

Anchor artifact: the first real `trimet/<day>/<HHMMSS>Z_vehiclepositions.pb.gz`
on disk with a matching `manifest.jsonl` line (sha256, redacted URL, HTTP 200).

## Scenario A — runs before any key exists
Given no `/home/claude/.config/pdxtrafficmonster/env`
When the service is started
Then it stays up (survives its systemd watchdog window), writes `status.json`
  with `keys_present` all false, makes no keyed request (only the keyless
  static-GTFS snapshot of Scenario F), and logs one "waiting" line per missing
  **credential** per hour — two, not three: `tomtom_tiles` and
  `tomtom_segments` share a single warning for the one absent TomTom key.
  The first pair appears when each source first comes *due* (which a restored
  schedule may defer past startup), not at the moment the process starts.

## Scenario B — a key added later is picked up without a restart
Given the service is running with no keys
When `TRIMET_APP_ID=...` is written to the env file
Then within one cycle (≤5 s) plus the source interval, a `.pb.gz` snapshot
  and a manifest line appear, and `status.json.keys_present.TRIMET_APP_ID` is true.

## Scenario C — TomTom daily caps hold
Given `PDXTM_TOMTOM_TILE_DAILY_CAP` is reached for today (UTC)
When the tile interval elapses
Then no tile requests are made, one "cap reached" warning is logged per hour,
  and requests resume after the UTC day rolls over.

## Scenario D — keys never leak
Given keys are configured
When any request is made (success or failure)
Then neither the journal nor any `manifest.jsonl` contains the key value
  (URLs are stored with `appID`/`key` replaced by `REDACTED`).

## Scenario E — failures are recorded, not hidden
Given a source returns non-200 (e.g. 403 bad AppID, 429 rate limit)
When the fetch completes
Then a manifest line records the status with `path: null`, no file is written,
  and that source's next attempt backs off (×2, capped) while others continue.
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

## Scenario G — TomTom stays off until the terms gate is opened
Given `TOMTOM_API_KEY` is present and `PDXTM_TOMTOM_ENABLED` is unset or not `1`
When the TomTom intervals elapse
Then no TomTom request is made, one "read the developer T&C" warning is logged
  per hour, and `status.json.tomtom_enabled` is false.

## Scenario H — one broken source cannot stall or overspend the others
Given a TomTom tile fetch raises mid-loop (disk full, read-only remount)
When the cycle completes
Then the tile budget for that cycle is already charged, the tile source is
  deferred (no refire on the next 5 s tick), and TriMet / segments still run.
And given the process is then killed and restarted (crash, watchdog, deploy)
Then the persisted schedule (`schedule.json`) is honoured, so the restart
  does not refire the tiles either — a crash loop cannot become a spend loop.

## Evidence
`bdd/collector/live-collector-evidence.md` (written at first real capture).
Unit tests: `python3 -m unittest tests.test_collect_live`.
