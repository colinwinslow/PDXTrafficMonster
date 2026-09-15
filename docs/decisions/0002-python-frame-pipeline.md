---
id: 0002
title: Rendering stack — Python frame pipeline (GeoPandas + matplotlib LineCollection → PNG frames → ffmpeg)
status: draft
date: 2026-09-15
supersedes: []
superseded-by: null
tags: [stack, rendering, python, pipeline]
---

# ADR-0002: Rendering stack — Python frame pipeline

## Context

ADR-0001 fixes the deliverable as a pre-rendered video of variable-width
ribbons on real road geometry. The inputs are already on disk in plain
formats: OSM road segments as GeoJSON `LineString`s (WGS84) and PORTAL
readings as flat JSON keyed by `detector_id` + `starttime`, with station
points in Web Mercator. The project is developed agentically under a
"verify on disk" rule and an "anchor artifact first" rule (`CLAUDE.md`), so
the stack has to make every intermediate inspectable by reading a file, and
has to produce one real frame before any supporting plumbing exists.
Candidates considered: a Python pipeline, deck.gl in headless Chrome, a
D3/Observable static site, Blender/Manim, QGIS temporal controller.

## Decision

**Render with a single-runtime Python pipeline: GeoPandas/Shapely for the
geometry and the station-to-segment join, pandas for the PORTAL readings,
matplotlib `LineCollection` with per-segment `linewidths` for the ribbons,
one PNG per frame written to disk, and ffmpeg to stitch the frames into an
MP4.** No browser, no GPU, no second runtime.

## Rationale

- **Every frame is an artifact.** A PNG on disk per timestep is exactly what
  "verify on disk" and BDD evidence want; the anchor artifact is literally
  frame 0. Bugs are diffed as images, not debugged in a headless browser.
- **`LineCollection` is the ribbon primitive.** Per-segment linewidth is a
  first-class parameter, so "volume → width along OSM geometry" is a direct
  mapping with no shader or path-simplification work.
- **One runtime, headless, deterministic.** Runs on the bridge box or in CI
  with `python` + `ffmpeg`; no Node, no Chrome, no frame-capture timing
  races. The pipeline is a plain script that can be re-run end-to-end from
  the committed samples.
- **Rejected — deck.gl + Puppeteer.** Prettier GPU rendering and a real
  `PathLayer`, but two runtimes and the frame-capture step is the fragile
  part (timing, resolution, WebGL in headless). Its strengths are
  interactivity, which ADR-0001 does not need.
- **Rejected — D3/Observable static site.** The right tool for an
  interactive page; wrong for a fixed video. Could host the MP4 later.
- **Rejected — Blender / Manim.** Beautiful, but the scene graph is opaque
  to review and the data join would live outside the renderer.
- **Rejected — QGIS temporal controller.** GUI-driven; not reproducible
  agentically.
- Rendering cost is a non-issue at this scale: hourly cadence over ~6 weeks
  is ~1,000 frames of a few hundred line segments each.

## Consequences

**Enables:**
- A testable core: the detector→station→segment join and the width-scaling
  function are pure pandas/GeoPandas and get red/green unit tests.
- Anchor artifact = `render_frame(timestamp)` → one PNG from one real hour.
- Straightforward provenance: a frame's metadata (timestamp, detector ids
  used) can be written alongside it.

**Constrains:**
- matplotlib aesthetics; polish (glow, easing, motion blur) is manual.
- No basemap unless a tile source (e.g. contextily / OSM tiles) is added,
  which brings attribution and tile-usage-policy questions — default is a
  dark background with the OSM road lines only.
- Python env must be pinned (GeoPandas/Shapely/pyproj versions matter for
  the CRS work; the station points are EPSG:3857 and the roads EPSG:4326).
- `CLAUDE.md` "Build & test" must be filled in behind this ADR at
  `/closeout` (invariant 3 says stack-dependent invariants get written once
  the stack is chosen).

**Open:**
- Visual style: palette, dark theme, how speed (if used) colors the ribbon —
  apply the `dataviz` skill when the first frame is styled.
- Frame resolution / fps / output size for the target channel.
- `uv` vs `pip` + `requirements.txt` for the env.
- Whether a minimal web page should host the MP4 (separate, later).

## References

- ADR-0001 — the concept this stack renders
- `docs/research/samples/README.md` — input formats (GeoJSON LineStrings,
  PORTAL JSON field names, CRS note)
- `CLAUDE.md` — "Verify on disk", "Anchor-artifact discipline", "Build & test"
