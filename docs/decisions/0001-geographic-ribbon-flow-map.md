---
id: 0001
title: Visualization concept — animated geographic ribbon flow map; freeway volume ribbons + live arterial congestion layer
status: draft
date: 2026-09-15
supersedes: []
superseded-by: null
tags: [visualization, concept, scope, data]
---

# ADR-0001: Visualization concept — animated geographic ribbon flow map; freeway volume ribbons + live arterial congestion layer

## Context

I-5 southbound through the Rose Quarter closed 2026-09-11 for ~5 weeks. The
project's premise is to show, from real measured data, how traffic reroutes
onto I-405, I-205, and the local grid. Several concept shapes were on the
table (abstract Sankey, speed heatmap over time, before/after split, live
dashboard). The real data samples (`docs/research/samples/`) settled what is
actually measurable: PORTAL provides hourly (and raw 20-second) volume and
speed at ~34 point stations along I-5 and I-405 near the closure (and more on
I-205), joined detector → station → highway, with station coordinates; OSM
provides the road centerlines with per-segment lane counts. PORTAL has **no**
measured data for any Portland surface street — its arterial stations are all
Clark County, WA, and its Bluetooth travel-time segments skip N/NE Portland
entirely — so the local-street diversion story needs other public sources.
Two exist, both live-only with no public history: TriMet's GTFS-realtime
vehicle positions (bus speed between stops as a congestion proxy; terms
explicitly permit redistribution) and TomTom's Traffic Flow API (probe-based
segment speeds, free tier, terms still to be read). Waze is excluded by
invariant 2. Because these sources start on the day collection starts
(2026-09-15), the pre-closure arterial baseline is already gone.

## Decision

**The visualization is an animated geographic flow map, pre-rendered to
video, in which variable-width ribbons follow the actual OSM road geometry of
I-5, I-405, and I-205, with ribbon width driven by measured PORTAL detector
volume, over the window 2026-09-01 (ten days of pre-closure baseline) through
reopening — plus an arterial congestion layer on the local diversion streets
(MLK Jr Blvd, Interstate Ave, Williams/Vancouver, Broadway/Weidler) drawn as
speed-colored lines, never volume-width, from two live sources collected from
2026-09-15 on: TriMet bus speeds between stops and TomTom probe speeds.** The
arterial layer's baseline is the post-reopening period, not pre-closure. Every
arterial reading is caveated on screen as proxy (TriMet) or probe (TomTom),
never as counted volume.

## Rationale

- **Geographic, not abstract.** The story is *where* the traffic goes — I-405
  hugging downtown vs. I-205 looping east. A Sankey layout throws away the one
  thing the audience already knows (the map) and the "monster" framing wants
  an organic thing crawling over a real city.
- **Ribbons (volume → width), not a heatmap.** A heatmap shows *state*
  (congestion); ribbons show *flow*. Volume is the quantity that actually
  moves between corridors; speed can ride along as color later.
- **Animated over the closure, not a static before/after.** The interesting
  part is the transition and the daily rhythm, and the animation is what the
  project name promises. Pre-rendered video (rather than an interactive site)
  keeps the deliverable a single reviewable artifact and matches the
  post-hoc, non-live scope in `CLAUDE.md`.
- **Arterials as speed color, not volume width — forced by what is measured.**
  The three PORTAL arterial surfaces are empty for Portland (samples README
  §3), so no surface street has a vehicle count. What *is* measurable is
  speed: TriMet buses report position every few seconds, and between stops a
  bus in congestion moves like the cars around it (in free flow, cars are
  faster — so the proxy under-reads speed only when it doesn't matter). TomTom
  probe speeds are the direct measurement and cross-check the proxy; two
  probe points sit on PORTAL loop stations so TomTom can be checked against
  loops too. Widening an arterial by anything but a count would violate
  invariant 1; coloring it by a measured speed does not.
- **Reopening as the arterial baseline.** Live-only sources cannot recover
  2026-09-01 → 09-14. Rather than fake a baseline, the arterial story is told
  closure → relief: the weeks after reopening are the "normal" the closure
  weeks are compared to. The freeway ribbons keep their real pre-closure
  baseline from PORTAL.
- **TriMet over Waze.** Waze for Cities is partner-only under an agreement
  that forbids republication and its live map is a ToS scrape (invariant 2).
  TriMet's API terms grant a license to "use, reproduce, redistribute and
  display" the data.
- **Start 2026-09-01, not 2026-09-11.** Ten days of baseline is what makes the
  closure visible as a *change* rather than as the only thing on screen.
  PORTAL retains it (verified: complete hourly data from 09-01).

## Consequences

**Enables:**
- A single pipeline shape: PORTAL reading → detector → station → nearest OSM
  segment(s) → per-frame ribbon width. Every width on screen traces to a
  `detector_id` and a `starttime` (invariant 1 satisfied by construction).
- The anchor artifact is obvious and small: one rendered frame of the three
  corridors with ribbon widths from one real hour of data.
- I-205 needs its sensor data pulled (only its metadata is in the sample);
  the pull is the same `freewaydata` call with `highway_id=3,4`.

**Constrains:**
- Ribbon width between stations is **assigned, not measured**: a segment
  between two stations inherits a station's value (rule to be fixed in the
  spec). The rendering must caveat this as station-level data drawn along a
  line, not a continuous measurement.
- The arterial layer says "slower/faster", never "how many". If the audience
  asks "how many cars moved to Interstate Ave?", this concept cannot answer.
- The arterial layer begins 2026-09-15, four days into the closure, and its
  quality depends on a collector that must keep running unattended on
  claude-box through reopening. A gap in collection is a gap on screen.
- Two more external dependencies (TriMet AppID, TomTom key), both registered
  by the human and kept off-repo in
  `/home/claude/.config/pdxtrafficmonster/env`.
- Video is a fixed narrative — no scrubbing, no hover. Interactivity would be
  a new ADR.

**Open:**
- TomTom developer terms (storage/redistribution of API responses) were not
  machine-readable; must be read at registration. If they forbid archiving
  raw responses, the TomTom layer drops to display-only or is removed by a
  superseding ADR.
- Bus-speed-between-stops derivation: which stop pairs, how to exclude dwell
  time, minimum samples per interval. Spec question.
- Segment ↔ station width rule (nearest station by milepost? upstream only?
  linear between neighbours with a caveat?). Spec question.
- Frame cadence: hourly is what the sample uses; 15-minute exists and may
  read better for the peaks.
- Speed as ribbon color, or volume only?
- Whether to include the WA side (WSDOT) for the Vancouver-commuter story.
- What defines "reopening" for the end of the window (ODOT announcement date),
  and how many post-reopening weeks the arterial baseline needs.

## References

- `docs/research/i5-closure-data-sources.md` — source survey
- `docs/research/samples/README.md` — the real pulls this decision is scoped
  against (§1 PORTAL freeway, §2 OSM, §3 PORTAL arterial = none, §4 TriMet +
  TomTom)
- `bdd/collector/live-collector-bdd.md`, `scripts/collect_live.py` — the
  collector this layer depends on
- ADR-0002 — rendering stack chosen to produce this
- `CLAUDE.md` invariant 1 (provenance over synthesis), "What is out of scope"
