# HANDOFF — PDXTrafficMonster

## Repository

```text
Local path:  /home/claude/repos/PDXTrafficMonster
GitHub:      https://github.com/colinwinslow/PDXTrafficMonster
Branch:      claude/sweet-turing-qmqv6u (all work so far; no PR yet)
```

## What this project is

PDXTrafficMonster is an animated data visualization of how Portland traffic
redirects during the five-week closure of I-5 southbound at the Rose Quarter
(closed starting 2026-09-11, reopening expected mid-October 2026). It's built
on real public traffic data — not a simulation — and the goal is to show
drivers visually rerouting onto I-405, I-205, and the surface street grid as
the closure squeezes the primary corridor.

## Current direction

Concept and stack are decided in ADR-0001 and ADR-0002 (see their `status`
for draft vs accepted). The deliverable is a pre-rendered video: ribbons on
real OSM road geometry for I-5/I-405/I-205, widened by PORTAL loop-detector
volume (real 2026-09-01 baseline, PORTAL archives it), plus an arterial layer
on MLK / Interstate / Williams-Vancouver / Broadway-Weidler colored by speed
only, from TriMet bus positions (a proxy — buses and cars move alike in
congestion, cars are faster in free flow). Live-only, collected from
2026-09-15, with the post-reopening weeks as its baseline. TomTom was evaluated
and removed on licence grounds (ADR-0001 amendment). Rendering is a Python pipeline (GeoPandas + matplotlib
LineCollection → PNG per frame → ffmpeg).

Two things a new session must know that the code doesn't say:

- **A collector is running on claude-box** (`pdxtrafficmonster-collector.service`,
  `scripts/collect_live.py`) writing to `/home/claude/data/pdxtrafficmonster/`
  (off-repo). It is idle until `TRIMET_APP_ID` exists in
  `/home/claude/.config/pdxtrafficmonster/env` (human registers; never paste
  keys into a chat). Static GTFS snapshots need no key and should already be
  landing weekly. Check `status.json` first thing; the
  running copy is `/usr/local/lib/pdxtrafficmonster/collect_live.py`, so a
  code change needs `scripts/install_collector.sh` to take effect.
- **PORTAL has no Portland arterial data** — checked three ways, recorded in
  `docs/research/samples/README.md` §3. Don't re-search it.

## Latest completed work

2026-09-15→16: real PORTAL + OSM samples with provenance
(`docs/research/samples/`), ADR-0001/0002 drafted, collector deployed and
Scenario A verified live (`bdd/collector/live-collector-evidence.md`).

## Recommended next step

Pipeline slice 1: `/spec render-frame` and produce the anchor artifact — one
PNG frame from one real PORTAL hour — before any other plumbing. Regenerate
the collector evidence the moment a key lands. See `STATUS.md`.

## Constraints / guardrails

- Don't use Waze data or scrape Google Maps traffic tiles — `CLAUDE.md`
  invariant 2. TriMet's API terms permit redistribution. **TomTom is settled:
  ruled out 2026-09-16, T&C §11.4 prohibits storing Results — do not re-add
  it** (ADR-0001 amendment, samples README §4).
- Arterials are speed-colored, never volume-widened — nothing on a surface
  street is counted (invariant 1).
- The closure is time-boxed (started 2026-09-11, ~5 weeks). Every uncollected
  day is a gap in the arterial layer; the freeway story is safe in PORTAL.
- Samples README gotchas: PORTAL `end_date` is exclusive; endpoints need the
  trailing slash; Overpass needs a `User-Agent`.
