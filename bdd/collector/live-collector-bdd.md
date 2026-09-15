# BDD: live collector (TriMet GTFS-RT + TomTom flow)

Feature: capture live-only arterial data on claude-box from the moment keys
exist, as raw bytes with provenance, without ever exposing a key.

Anchor artifact: the first real `trimet/<day>/<HHMMSS>Z_vehiclepositions.pb.gz`
on disk with a matching `manifest.jsonl` line (sha256, redacted URL, HTTP 200).

## Scenario A — runs before any key exists
Given no `/home/claude/.config/pdxtrafficmonster/env`
When the service is started
Then it stays up, writes `status.json` with `keys_present` all false,
  makes zero outbound requests, and logs one "waiting" line per source per hour.

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

## Evidence
`bdd/collector/live-collector-evidence.md` (written at first real capture).
Unit tests: `python3 -m unittest tests.test_collect_live`.
