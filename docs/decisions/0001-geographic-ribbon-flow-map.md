---
id: 0001
title: Visualization concept — animated geographic ribbon flow map; freeway volume ribbons + TriMet-proxy arterial layer
status: draft
date: 2026-09-15
supersedes: []
superseded-by: null
tags: [visualization, concept, scope, data]
---

# ADR-0001: Visualization concept — animated geographic ribbon flow map; freeway volume ribbons + TriMet-proxy arterial layer

> **Amended 2026-09-16** (still `draft`, so amended in place rather than
> superseded). TomTom is removed from this decision: its developer T&C, read
> after the original draft, prohibits storing API Results at all. The arterial
> layer is now TriMet-only. Original text kept below except where it named
> TomTom; the amendment is marked inline.

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
Two candidates existed, both live-only with no public history: TriMet's
GTFS-realtime vehicle positions (bus speed between stops as a congestion proxy;
terms explicitly permit redistribution) and TomTom's Traffic Flow API
(probe-based segment speeds, free tier). Waze is excluded by invariant 2.
Because these sources start on the day collection starts (2026-09-15), the
pre-closure arterial baseline is already gone.

**Amendment 2026-09-16 — TomTom is out.** Its Portal T&C §11.4 prohibits
"caching or storing of any Results" outside a client-side cache bounded by the
response's own `max-age`; §11.6.1 forbids deriving a secondary database;
§20.2.3 is a warranty against combining Licensed Products with data that would
subject them to a copyleft licence, and our geometry is ODbL OSM (named in
§1's Open Source License definition); and §2.1/2.2 grant a licence only for a
"Permitted Solution" (requires Asset Management Functionality, which this
project lacks) or "Evaluation Use" (defined as *internal* evaluation). Any one
of those rules it out; together they leave no configuration in which this
project may store TomTom Results. Full citations in
`docs/research/samples/README.md` §4. The arterial layer is therefore
**TriMet-only**.

## Decision

**The visualization is an animated geographic flow map, pre-rendered to
video, in which variable-width ribbons follow the actual OSM road geometry of
I-5, I-405, and I-205, with ribbon width driven by measured PORTAL detector
volume, over the window 2026-09-01 (ten days of pre-closure baseline) through
reopening — plus an arterial congestion layer on the local diversion streets
(MLK Jr Blvd, Interstate Ave, Williams/Vancouver, Broadway/Weidler) drawn as
speed-colored lines, never volume-width, derived from TriMet bus speeds between
stops, collected live from 2026-09-15 on.** The
arterial layer's baseline is the post-reopening period, not pre-closure. Every
arterial reading is caveated on screen as a **transit proxy**, never as counted
volume and never as measured car speed.

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
  faster — so the proxy under-reads speed only when it doesn't matter).
  Widening an arterial by anything but a count would violate invariant 1;
  coloring it by a measured speed does not.
- **The proxy now stands alone, and that is a real weakening.** The original
  draft paired it with TomTom probe speeds as an independent check, including
  two probe points placed on PORTAL loop stations 3121/3169 so probe speed
  could be validated against loop speed at the same spot. The licence removed
  that. What remains is one indirect measurement with no second opinion, which
  raises the bar on how the layer is captioned.
- **Reopening as the arterial baseline.** Live-only sources cannot recover
  2026-09-01 → 09-14. Rather than fake a baseline, the arterial story is told
  closure → relief: the weeks after reopening are the "normal" the closure
  weeks are compared to. The freeway ribbons keep their real pre-closure
  baseline from PORTAL.
- **TriMet over Waze and TomTom.** Waze for Cities is partner-only under an
  agreement that forbids republication and its live map is a ToS scrape
  (invariant 2). TomTom forbids storing Results at all (see amendment above).
  TriMet's API terms §5 grant a licence to "use, reproduce, redistribute and
  display" the data — the only one of the three compatible with a public repo.
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
- One external dependency (TriMet AppID), registered by the human and kept
  off-repo in `/home/claude/.config/pdxtrafficmonster/env`.
- The arterial layer has no independent validation source. If the bus proxy
  turns out to be unusable (too few buses per interval, dwell time
  contaminating segment speeds), there is no fallback and the layer is dropped
  rather than replaced.
- Video is a fixed narrative — no scrubbing, no hover. Interactivity would be
  a new ADR.

**Open:**
- ~~TomTom developer terms~~ — **RESOLVED 2026-09-16: prohibited, removed.**
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
