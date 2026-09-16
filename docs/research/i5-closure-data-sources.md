---
title: Public data sources for the I-5 southbound Rose Quarter closure
status: promoted-to-adr
date: 2026-09-14
promoted: 2026-09-16
---

# Research: Public data sources for the I-5 southbound Rose Quarter closure

## Question

What publicly available data can drive an animated visualization of how
Portland traffic redirects during the five-week closure of I-5 southbound
through the Rose Quarter?

## Context

ODOT closed I-5 southbound through the Rose Quarter starting the night of
2026-09-11, for up to five weeks, to repave a 2-mile stretch (last done 1985)
and seismically retrofit the highway as part of the I-5 Rose Quarter
Improvement Project. Officials expect travel times 2-3x normal during peak
periods, with backups extending into Washington. Named alternates: I-405
(through downtown), I-205 (bypassing the city entirely), and the MAX Yellow
Line for Vancouver-North Portland-downtown trips.

This note surveys what data exists to actually visualize the redirect, ahead
of choosing a visualization concept or tech stack (the first ADR).

## Notes

### Tier 1 — best fit (free, public, no partnership gate)

**PORTAL — Portland transportation data archive (PSU)**
https://portal.its.pdx.edu/
Freely and publicly downloadable, no account/partnership required. Archives
freeway loop-detector data (speed/volume/occupancy, 20-second raw plus
aggregated) from the region's ~436 ATMS sensors, arterial signal data,
Bluetooth-derived travel times, transit data, and bike counts, back to 2004.
This is the only source with real speed/volume data across I-5, I-405, and
I-205 simultaneously — the core of the "how traffic redirects" story. Leading
candidate for the primary data source. Not yet confirmed: exact field names,
file format, and whether recent (2026-09) data is available with low lag —
needs a real sample pull before committing.

**ODOT TripCheck Data API**
https://apiportal.odot.state.or.us/product/tripcheck-data-api
Free, register for a public API key. Endpoints: incidents (2-min refresh),
local-agency incidents, dynamic message sign inventory + live content (2-min
refresh), camera inventory, RWIS weather (15-min refresh). Good for event
annotations/overlays (e.g. "DMS warns of 45-min backup") layered on top of
the PORTAL flow data, not a flow-data source itself.

**WSDOT Traveler Information API**
https://wsdot.wa.gov/traffic/api/
Free, register via email for an access code. Matters because a large share of
diverted traffic is Vancouver, WA commuters — gives current + average travel
times on the WA side (I-5, SR-14, I-205 north of the river).

### Tier 2 — supporting/context data

- **PBOT / PortlandMaps open data** —
  https://gis-pdx.opendata.arcgis.com/datasets/traffic-volume-counts
  City street-level traffic volume counts (AADT). Baseline-only, not live
  during the closure — useful for local-street diversion context (e.g.
  Interstate Ave, MLK Jr Blvd) but not for showing the redirect in motion.
- **TriMet GTFS-realtime** — https://developer.trimet.org/
  Vehicle positions/trip updates for the MAX Yellow Line, the official rail
  alternative through the closure zone. Could support a transit-ridership-
  shift layer alongside the road data.
- **TomTom Traffic Index / Move portal** — https://www.tomtom.com/traffic-index/
  Free congestion-index CSVs by city and hour. Decent for a simple headline
  stat ("Portland got X% slower during the closure") but not granular enough
  for route-level animation.

### Dead ends

- **Waze Connected Citizens Program** — real-time incident/jam data, but
  requires being an official government/nonprofit partner under a signed
  agreement that explicitly forbids republishing the raw data publicly. Not
  accessible for a personal/public project.
- **Google Maps historical/live traffic data** — no public API for this; the
  real feed (BigQuery historical-roads data exchange) is an enterprise
  product. Scraping the Maps traffic tiles would violate Google's terms of
  service — ruled out entirely, not just deferred.

### The closure's own web presence

https://i5rosequarter.org/current-construction-travel-impacts/ has no live
dashboard or data feed of its own — it points visitors to TripCheck for
real-time info and offers static closure maps/fact sheets only.

## Open sub-questions

- What does a real PORTAL data pull actually look like (station IDs near the
  Rose Quarter, field names, granularity, latency)? Needed before the stack
  ADR.
- Is 5 weeks (2026-09-11 through roughly mid-October) actually enough
  before/during/after data to tell a clean redirect story, or do we need to
  start pulling now and worry about "after" data once the reopening date is
  confirmed?
- Does the visualization need to be built and published *during* the closure
  (timely, but rushed) or can it be a retrospective built after reopening
  with the full window of data in hand?

## Resolution

Promoted 2026-09-16 to ADR-0001 (concept + sources) and ADR-0002 (stack),
with ADR-0003 recording the collect-before-anchor exception. What the real
pulls changed relative to this note (`docs/research/samples/README.md`):

- PORTAL confirmed as primary — open API, no auth, hourly + raw 20 s, data
  complete to ~18 h behind real time. **But PORTAL has no Portland arterial
  data** (arterial stations are all Clark County WA; Bluetooth segments skip
  N/NE Portland) — the "arterial signal data" line in Tier 1 above does not
  apply to this project's streets.
- The local-street layer therefore comes from TriMet GTFS-realtime (bus speed
  between stops as a congestion proxy; terms permit redistribution) and TomTom
  Traffic Flow (probe speeds; free tier; developer T&C still to read). Both
  are live-only, collected from 2026-09-15 by `scripts/collect_live.py`.
- The three open sub-questions: (1) answered in the samples README; (2) the
  freeway story has a real 09-01 baseline, the arterial story uses
  post-reopening as its baseline; (3) retrospective build, but collection
  had to start immediately — hence ADR-0003.
