# Data samples — provenance notes

Pulled 2026-09-15 from a network-unrestricted session (the sandboxed cloud
session that started this research could not reach any of these domains —
this pull was done from a different machine specifically to get past that
egress block). Everything in this directory is real data pulled live over
the network with the commands below — nothing here is fabricated,
estimated, or hand-written. Re-run the commands to reproduce.

## 1. PORTAL (Portland transportation data archive, PSU)

- Site: https://portal.its.pdx.edu/ — redirects (301) to
  **https://new.portal.its.pdx.edu/**, which is the live site as of
  2026-09-15. Both domains work; use the `new.` host directly to skip the
  redirect.
- No account, API key, or auth of any kind was needed for any endpoint
  below.
- API base discovered by inspecting the "Data Downloads" page
  (`/downloads/`) form markup — each form's `data-apibase` attribute is the
  real REST endpoint: `/highways/api/stationmetadata/`,
  `/highways/api/detectormetadata/`, `/highways/api/highwaymetadata/`,
  `/highways/api/freewaydata/`. Human-readable API docs live at
  https://adus.github.io/portal-documentation/ but don't fully enumerate
  query params — the download-form HTML was the more reliable source of
  truth for exact parameter names.

### Endpoints pulled

All of these need a **trailing slash** — without it the server 301s to the
slash form and curl needs `-L` (or just always call with the trailing
slash, which is what the commands below do).

| File | Endpoint | Format |
|---|---|---|
| `portal_station_metadata_full.json` | `GET /highways/api/stationmetadata/` | GeoJSON FeatureCollection, 619 stations, all regions PORTAL covers (not just Portland — includes Salem, Eugene/R2, Bend/R4, WA SR-14/I-205/I-5) |
| `portal_detector_metadata_full.json` | `GET /highways/api/detectormetadata/` | flat JSON list, 1,555 detectors (each station has 1+ detector, one per lane) |
| `portal_highway_metadata.json` | `GET /highways/api/highwaymetadata/` | flat JSON list — maps `highwayid` → name + direction, e.g. `highwayid 1` = "I-5" NORTH, `2` = "I-5" SOUTH, `5`/`6` = I-405 N/S, `3`/`4` = I-205 N/S |
| `portal_rosequarter_i5_i405_hourly_20260901_20260914.json` | `GET /highways/api/freewaydata/?start_date=2026-09-01&end_date=2026-09-15&days_of_week=1..7&format=json&highway_id=1&highway_id=2&highway_id=5&highway_id=6&resolution=01:00:00` | flat JSON list, hourly-aggregated speed/volume, **filtered client-side down to the 83 detectors at the 34 Rose-Quarter-area stations** (see below) |
| `portal_rosequarter_i5split_raw20s_20260911_sample.json` | same endpoint, `resolution=00:00:20`, `highway_id=1` only, `start_date=2026-09-11&end_date=2026-09-12`, filtered client-side to the 2 detectors at station 3171 (NB I-5 at the I-405 split, MP 303.47) | flat JSON list — demonstrates true 20-second raw granularity is real and downloadable, not just the aggregated resolutions |
| `portal_rosequarter_stations_and_detectors.json` | derived (not a direct pull) | curated join of station + detector metadata, restricted to the Rose-Quarter-area station set, with Web Mercator coords converted to lon/lat for convenience |

Exact commands (from repo root):

```bash
curl -s "https://new.portal.its.pdx.edu/highways/api/stationmetadata/" -o portal_station_metadata_full.json
curl -s "https://new.portal.its.pdx.edu/highways/api/detectormetadata/" -o portal_detector_metadata_full.json
curl -s "https://new.portal.its.pdx.edu/highways/api/highwaymetadata/"  -o portal_highway_metadata.json

curl -s "https://new.portal.its.pdx.edu/highways/api/freewaydata/?start_date=2026-09-01&end_date=2026-09-15&days_of_week=1&days_of_week=2&days_of_week=3&days_of_week=4&days_of_week=5&days_of_week=6&days_of_week=7&format=json&highway_id=1&highway_id=2&highway_id=5&highway_id=6&resolution=01:00:00" \
  -o /tmp/rq_corridor_hourly_full.json   # then filtered client-side to Rose-Quarter detector_ids

curl -s "https://new.portal.its.pdx.edu/highways/api/freewaydata/?start_date=2026-09-11&end_date=2026-09-12&days_of_week=1&days_of_week=2&days_of_week=3&days_of_week=4&days_of_week=5&days_of_week=6&days_of_week=7&format=json&highway_id=1&resolution=00:00:20" \
  -o /tmp/raw20s_probe2.json   # then filtered client-side to detector_ids 101024,101025
```

### Field names, confirmed by real response payloads

**Station metadata** (`portal_station_metadata_full.json`, GeoJSON `properties`):
`stationid`, `highwayid`, `milepost`, `locationtext` (human-readable, e.g.
`"Broadway (2DS010) @ SB I-5 MP302.51"`), `length`, `agencyid`,
`active_dates` (a stringified `{"bounds": "[)", "lower": ..., "upper": ...}`
range — `upper: null` means still active). `geometry.coordinates` are
**Web Mercator (EPSG:3857), not lon/lat** — confirmed by converting station
3171 (NB I-5 @ I-405 split, the closest sensor to the Rose Quarter arena)
and getting `-122.6784, 45.5472`, which lands correctly on I-5 right at the
Rose Quarter/I-405 split. The curated join file converts these to lon/lat.

**Detector metadata**: `detectorid`, `stationid` (join key back to
stations), `highwayid`, `milepost`, `detectortitle`, `lanenumber`,
`agency_lane`, `active_dates`. One row per physical lane at a station.

**Highway metadata**: `highwayid`, `direction` (`NORTH`/`SOUTH`/etc),
`highwayname` (e.g. `"I-5"`, `"I-405"`), `oppositehighwayid`.

**Freeway data, aggregated resolutions (1hr/5min/15min/day/month/year)**:
`id`, `starttime` (ISO 8601 with `-07:00` offset — Pacific time, pre-computed,
not UTC), `volume` (vehicle count), `speed` (mph), `occupancy` (% of time
loop was occupied), `countreadings` (how many raw 20s samples fed the
aggregate — data-quality signal), `vmt`, `vht`, `delay`, `traveltime`,
`resolution`, `detector_id` (join key to detector metadata, **not**
`stationid` directly — you join detector → station → highway to place a
reading on the map).

**Freeway data, raw 20-second resolution**: different field set than the
aggregates — `id`, `detector_id`, `start_time` (note: underscore, not
`starttime` like the aggregated endpoint — a real naming inconsistency
between resolutions, not a typo on our part), `volume`, `speed`,
`occupancy`, `reliability` (%, data-quality signal replacing
`countreadings`). No `vmt`/`vht`/`delay`/`traveltime` at raw resolution —
those are only computed at aggregated resolutions.

### Access friction encountered

- **No auth needed anywhere** — every endpoint above is open. This is
  better than the tier-1 assessment in
  `docs/research/i5-closure-data-sources.md` assumed (that note flagged
  "not yet confirmed" on format/auth).
- **Trailing-slash 301s**: hitting `/highways/api/stationmetadata`
  (no trailing slash) 301-redirects to the slash form with an empty body —
  easy to silently get a 0-byte "success." Always call with the trailing
  slash.
- **`end_date` is exclusive, half-open, and this matters a lot**: querying
  `start_date=2026-09-11&end_date=2026-09-11` (same day) returns data for
  only the single `00:00:00` instant — effectively an empty query — **for
  every resolution**, not just raw. You must pass
  `end_date = start_date + 1 day` to get a full day. This cost real
  debugging time (first 20-second-resolution pull looked like the API just
  didn't support raw granularity for a full day; it was the date-range
  bug). The station `active_dates` field's own `"bounds": "[)"` tells you
  this convention is deliberate and consistent site-wide.
- **No per-station/per-detector filter on `freewaydata`** — the query API
  only filters by `highway_id` (whole highway, both directions listed
  separately as different IDs). To get "just the Rose Quarter sensors" you
  have to pull the whole highway for your date range and filter
  client-side by `detector_id` (via the detector→station join). This is
  why the hourly Rose-Quarter file is a filtered subset of a ~14MB/4-highway
  pull rather than a direct targeted download.
- **Raw 20-second data is genuinely retained historically** (not just a
  live/recent window) — the 2026-09-11 pull above is 5 days before the
  pull date and full-density (4,117 distinct 20-second timestamps across
  the full day for highway_id=1 alone, ~350k rows for all I-5 NB detectors
  that day). Good sign for building a real animation off raw data if
  needed, though the aggregated resolutions are almost certainly what a
  visualization would actually consume day-to-day.
- **Data lag**: as of the pull (~08:16 Pacific, 2026-09-15), 2026-09-13 is
  the most recent *complete* day (25 hourly timestamps for highway_id=1,
  matching every prior full day). 2026-09-14 is present but partial — only
  15 of 24 hourly timestamps (00:00 through 14:00 Pacific), i.e. ingestion
  lags roughly 18 hours behind real time. 2026-09-15 (pull date) returns
  zero records. **The corridor sample file
  (`portal_rosequarter_i5_i405_hourly_20260901_20260914.json`) includes
  this partial 09-14 — any consumer needs to treat the last day in the
  file as incomplete rather than trim it.** So as of this pull, usable
  *complete* data runs through 2026-09-13, with 09-14 partially populated
  and catching up. This directly answers STATUS.md open-queue item (b).
  (Note: this specific number — 72 records — was an earlier miscount
  caused by hitting the `end_date` exclusivity bug above with
  `start_date=end_date=2026-09-14`; re-querying with the correct
  `end_date=2026-09-15` gives the accurate 15-hour partial count reported
  here.)

### Rose-Quarter-area station selection

34 stations / 83 detectors, selected as: all I-5 stations (`highwayid`
1 or 2) with milepost between 300.5 and 304.5 (covers Morrison Bridge south
of the Rose Quarter through Going St north of it, including the Broadway,
Wheeler, Russell, Greeley, and I-5/I-405-split stations right at the
closure), plus **all** I-405 stations (`highwayid` 5 or 6 — I-405 is short
enough, ~4 miles, that the whole loop is relevant to "where does I-5
traffic reroute to"). I-205 was **not** pulled for actual sensor data in
this sample (out of the immediate Rose Quarter milepost window) — the full
station list in `portal_station_metadata_full.json` has I-205 stations
(`highwayid` 3/4) too if/when the concept needs the wider bypass route.

## 2. OpenStreetMap road network — Overpass API

- Endpoint: `https://overpass-api.de/api/interpreter` (POST, query as
  `data` form field). No auth, no account, no rate-limit hit for a single
  query this size.
- **Access friction**: a request with no `User-Agent` header gets a bare
  `406 Not Acceptable` with no explanation. Overpass's public instance
  expects a real UA identifying the client (per its usage policy) — this
  is exactly the failure mode a generic HTTP client / bot hits by default.
  Fixed by sending `User-Agent: PDXTrafficMonster-research/0.1
  (colinwinslow@gmail.com)`.
- Query (saved verbatim at `osm_overpass_query.txt`): pulls all ways
  tagged `ref` matching exactly `I 5`, `I 405`, or `I 205`
  (`highway=motorway`/`motorway_link` etc.), plus ways named "North
  Interstate Avenue" or matching "Martin Luther King" (covers all the MLK
  Jr Blvd name variants — NE/N/SE segments, "Junior"/"Jr" spelling
  differences), all within a bounding box covering the Portland–Vancouver
  metro (45.35–45.70 N, -122.85– -122.45 W — roughly Oregon City to
  Vancouver WA, west hills to Gresham).

```bash
curl -s -X POST \
  -H "User-Agent: PDXTrafficMonster-research/0.1 (colinwinslow@gmail.com)" \
  --data-urlencode "data@osm_overpass_query.txt" \
  https://overpass-api.de/api/interpreter -o /tmp/overpass_result.json
```

Then converted from Overpass's native JSON (`out geom` gives each way's
node coordinates inline, no separate node lookup needed) to a standard
GeoJSON `FeatureCollection` of `LineString`s, one per way segment, with all
OSM tags preserved as GeoJSON `properties` (`highway`, `lanes`, `maxspeed`,
`ref`, `name`, `official_name`, etc.) — saved as
`osm_portland_rosequarter_corridors.geojson`.

### Confirmed contents

917 way segments total:

- **244** segments tagged `ref=I 5`
- **238** segments tagged `ref=I 205`
- **41** segments tagged `ref=I 405`
- **206** segments tagged `ref=OR 99E` — these are *not* a stray match:
  North/NE Interstate Avenue is concurrently signed as OR-99E, so ways
  matched by the `name="North Interstate Avenue"` clause carry that ref.
  Real-world co-signing, confirmed by spot-checking a few elements' `name`
  vs `ref` tags together.
- Remainder: MLK Jr Blvd segments (`name` variants: "Northeast Martin
  Luther King Junior Boulevard", "North Martin Luther King Junior
  Boulevard", "Southeast Martin Luther King Jr Boulevard", etc. — OSM
  hasn't normalized the "Junior"/"Jr" spelling across segments) and named
  bridges the ref-tagged ways cross (Marquam Bridge, Glenn L. Jackson
  Memorial Bridge, Interstate Bridge, Abernethy Bridge) which came along
  for free since they carry the same `ref` tags as the highway they carry.

Each `LineString` feature carries real per-segment attributes useful for
width/capacity encoding later — spot-checked example (I-5 way `5390509`,
near Barbur/Capitol Hwy): `highway=motorway`, `lanes=3`,
`maxspeed="55 mph"`, `oneway=yes`, plus turn-lane and destination-sign
tags. Geometry is standard WGS84 lon/lat pairs (`[lon, lat]` per GeoJSON
spec) — spot-checked coordinates land inside the declared bounding box and
on real Portland-area roads.

## 3. PORTAL arterial / travel-time — checked for local-street coverage (none)

Pulled 2026-09-15 (same session, ~7 hours after §1) specifically to answer:
does PORTAL have measured data for the Rose Quarter's local diversion
streets (Interstate Ave, MLK Jr Blvd, Broadway/Weidler, Williams/Vancouver)?
**Answer: no.** Three independent PORTAL surfaces, all negative:

| File | Endpoint | Result |
|---|---|---|
| `portal_arterial_stationlist.json` | `GET /arterial/stationlist/` (found in the arterial page's JS bundle, not on the downloads page) | GeoJSON, **80 stations, every one `agency: "Clark County"`** (WA). Zero stations inside a Portland-city bounding box (45.45–45.62 N, -122.75– -122.55 W). Fields: `stationid`, `reference_id`, `location`, `direction`, `lat`, `lon`, `reliability`, `agency`, `lanecount`. |
| `portal_traveltime_segment_inventory.json` | `GET /traveltime/api/seginventory/` | flat JSON, 461 segments (`source_system`: DAC 237 = freeway, TravelTime 180 = Bluetooth arterial, 41 null = WA freeways, ATMS 3). The Bluetooth arterial segments cover Powell/Foster/82nd/Sandy/Division/McLoughlin (SE), Barbur/Capitol/Macadam (SW), Beaverton/Hillsboro, US-26 Mt Hood, US-101. **None on any N/NE Portland arterial.** The only "Broadway" hits are the I-5/I-405 freeway ramps at Broadway. |
| (not saved — empty) | `GET /arterial/api/voyagevolume/?start_date=…&end_date=…&format=json` — the downloads page's "Voyage Volume" form, whose only params are `start_date`, `end_date`, `format` (no location selector) | **`[]` for every range tried**: 2026-09-10→11, 2025-09-10→11, 2024-09-10→11. Either dormant or needs an undocumented param; not usable as-is. |
| (404) | `GET /arterial/data_availability/` | referenced by the arterial page's JS but returns 404. |

```bash
curl -s "https://new.portal.its.pdx.edu/arterial/stationlist/"              -o portal_arterial_stationlist.json
curl -s "https://new.portal.its.pdx.edu/traveltime/api/seginventory/"        -o portal_traveltime_segment_inventory.json
curl -s "https://new.portal.its.pdx.edu/arterial/api/voyagevolume/?start_date=2026-09-10&end_date=2026-09-11&format=json"   # -> []
```

Endpoint discovery note: the arterial page (`/arterial/`) has no
`data-apibase` forms; its endpoints (`/arterial/stationlist/`,
`/arterial/onequantitycomp/`, `/arterial/twoquantities/`,
`/arterial/data_availability/`) were found by grepping the compiled bundle
`/static/CACHE/js/output.9542a92c5444.js`. The hash in that filename will
change on the next PORTAL deploy.

Consequence for the project: any surface-street layer would have to come
from a non-PORTAL source (PBOT's static AADT counts are baseline-only, not
closure-period) and would need an invariant-1 caveat. Recorded in ADR-0001.

## 4. TriMet (bus positions as an arterial congestion proxy) and TomTom (probe speeds)

Pulled/probed 2026-09-15 after §3 ruled out PORTAL for surface streets.
Both are **live-only** — neither has a public history — so the project's
collector (`scripts/collect_live.py`, deployed on claude-box as
`pdxtrafficmonster-collector.service`) archives raw responses from the moment
keys exist. Captured data lands **outside the repo** at
`/home/claude/data/pdxtrafficmonster/<source>/<UTC day>/…gz` with a
`manifest.jsonl` (redacted URL, HTTP status, bytes, sha256) per source.

### TriMet

| Item | Finding |
|---|---|
| Static GTFS | `https://developer.trimet.org/schedule/gtfs.zip` — public, **no key**, 29.5 MB, `Last-Modified: 2026-09-10`. `feed_info.txt`: version `20260823-20260910-0900`, valid 2026-08-23 → 2027-02-27, so it spans the closure. Saved: `trimet_gtfs/{agency,routes,route_directions,calendar,calendar_dates,feed_info}.txt` plus `trimet_gtfs/trimet_arterial_route_shapes.geojson` — 159 `shape_id` LineStrings for routes 4, 6, 8, 17, 24, 35, 44, 72, 75 (route 6 = "Martin Luther King Jr Blvd", 35 = "Macadam/Greeley", 44 = "Capitol Hwy/N Rosa Parks", 4 = "Fessenden/Woodstock"). `stop_times.txt` (156 MB) and full `shapes.txt` (29 MB) deliberately not committed; re-download to regenerate. |
| GTFS-realtime | `https://developer.trimet.org/ws/V1/VehiclePositions` (protobuf). **Requires an AppID**: without one the server returns `403 A valid appID is required to access this resource.` Free registration at `https://developer.trimet.org/appid/registration/`. TripUpdate and Alerts feeds exist at `/ws/V1/TripUpdate/` and `/ws/V1/FeedSpecAlerts/`. |
| Terms | `developer.trimet.org/terms_of_use.shtml` §5 (Web Services API): *"TriMet grants you a limited, revocable license to use, reproduce, redistribute and display the Data"* — explicitly redistributable, so invariant 2 is satisfied. Page is served as ISO-8859-1 (a UTF-8 read throws). |
| PORTAL transit archive | `/transit/downloadquarterlydata` offers only quarterly `passenger-census-*` snapshots (2019–2024, stop-level load); `/trimetvisual/` is quarterly load heatmaps. **No vehicle-speed history anywhere on PORTAL.** |

Proxy caveat, to be stated on the visualization: between stops, buses and
cars move at similar speeds in congestion; in free-flow, cars are faster. So
bus-derived speed is a congestion indicator, not a car-speed measurement.

### TomTom Traffic API

| Item | Finding |
|---|---|
| Flow Segment Data | `GET https://api.tomtom.com/traffic/services/4/flowSegmentData/{style}/{zoom}/json?key=…&point=lat,lon&unit=MPH`. Snaps to the nearest road fragment; response fields confirmed from the reference page (`docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data`): `frc`, `currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, `freeFlowTravelTime`, `confidence`, `roadClosure`, `coordinates`, optional `openlr`. **Free tier: 20K requests/month** ("Traffic Flow API — Segment Data", pricing page). |
| Vector Flow Tiles | `GET https://api.tomtom.com/traffic/map/4/tile/flow/{style}/{z}/{x}/{y}.pbf?key=…`, styles `absolute` / `relative` / `relative-delay` / `reduced-sensitivity`. One tile carries every segment's speed in its area — far better coverage per request. **Free tier: 200K/month.** (Traffic *Incidents* Details is the 2.5K/month product — easy to confuse.) |
| Terms | `docs.tomtom.com/legal/terms-and-conditions` is JavaScript-rendered and returned no readable text to curl; the consumer-site terms (`tomtom.com/en-gb/legal/terms-of-use/`) don't govern the API. **Open: read the developer T&C at registration for storage/redistribution limits** — recorded in ADR-0001. |
| Key | Free developer key, registration at `developer.tomtom.com`. Not yet registered as of this pull. |

Collector budget (defaults in `scripts/collect_live.py`): tiles at z14 over
bbox 45.52,-122.70 → 45.58,-122.64 (`absolute` style; exactly 20 tiles) every
5 min, capped 5,500/day (≈170K/31 days vs the 200K tier); six Flow Segment
probe points every 20 min, capped 600/day (≈13K/31 days vs 20K). **TomTom is
disabled by default** (`PDXTM_TOMTOM_ENABLED=0`) until the developer T&C has
been read — the key alone does not start collection (ADR-0003). The static
`gtfs.zip` is snapshotted weekly with no key, so the feed version behind any
archived bus position is always on disk. Probe
points were derived from the OSM sample (way midpoints on MLK @ Broadway, MLK
@ Fremont, Interstate @ Russell, Interstate @ Going) plus PORTAL stations 3121
and 3169 (SB/NB I-5 @ Broadway) so TomTom probe speed can be checked directly
against PORTAL loop speed at the same spot. A first OSM-nearest-way attempt
for the freeway points landed 587 m off and merged NB/SB — station coordinates
are the right anchor there.

## What wasn't pulled

- ODOT TripCheck API and WSDOT Traveler Information API (both need a
  registered key — out of scope for this pull, which focused on the two
  anchor sources needed for the stack decision: PORTAL for flow data, OSM
  for road geometry).
- I-205 sensor *data* (station/detector metadata for I-205 is present in
  the full PORTAL metadata pulls, just not included in the curated
  Rose-Quarter hourly sample — see selection note above).
- Anything for dates after 2026-09-13 (complete) / partial 2026-09-14 —
  not a choice, that's where PORTAL's own ingestion currently ends as of
  the 2026-09-15 pull.
