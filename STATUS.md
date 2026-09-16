# STATUS.md

**Last updated:** 2026-09-16 (concept + stack ADRs drafted; live collector deployed)
**Phase:** Phase 0 — research & framing (ADR-0001/0002 drafted, pending acceptance)
**Next bounded packet:** Pipeline slice 1 — the anchor artifact: one rendered PNG frame of I-5/I-405 ribbons on OSM geometry from one real PORTAL hour (ADR-0002), with a spec + BDD via `/spec`
**Current readiness:** READY-FOR-NEXT-PACKET (arterial collector idle until keys land — see Blockers)

## Recent sessions (rolling, last 5)

- **2026-09-15→16** — `samples+adrs+collector` — Pulled real PORTAL freeway
  data (34 Rose Quarter stations, hourly 09-01→09-14, raw 20 s proven) and
  OSM corridor geometry; confirmed PORTAL has no Portland arterial data.
  Drafted ADR-0001 (geographic ribbon map: freeway volume ribbons + arterial
  speed layer from TriMet proxy + TomTom probes) and ADR-0002 (Python frame
  pipeline). Deployed the live collector on claude-box; Scenario A verified
  live, B–E await keys (`bdd/collector/live-collector-evidence.md`).
- **2026-09-14** — `repo-seed` — Created the PDXTrafficMonster repo, installed
  the Claude Code agentic workflow kit (CLAUDE.md, `.claude/`, STATUS/HANDOFF,
  docs/bdd scaffolding), and seeded `docs/research/i5-closure-data-sources.md`
  from a prior research session surveying ODOT/PBOT/WSDOT/PORTAL/TriMet/Waze/
  Google/TomTom as candidate data sources. No code yet.

## Active work

### Decide visualization concept + tech stack — CLOSED 2026-09-15 (as drafts)

- [x] Concept: animated geographic ribbon flow map, pre-rendered video —
      ADR-0001
- [x] Primary source confirmed by real pull: PORTAL freeway loops, hourly +
      raw 20 s, no auth — `docs/research/samples/README.md` §1
- [x] Rendering stack: Python frame pipeline → PNG → ffmpeg — ADR-0002
- [x] Window: 2026-09-01 (baseline) → reopening; arterial layer from
      2026-09-15 with reopening as its baseline — ADR-0001

### Live arterial collection (running, keyless)

- [ ] **Human:** register TriMet AppID + TomTom key; write both to
      `/home/claude/.config/pdxtrafficmonster/env` on claude-box, owned by
      `claude` (no restart needed). Read TomTom developer T&C for
      storage/redistribution at signup, then add `PDXTM_TOMTOM_ENABLED=1` —
      TomTom does not collect until that line exists (ADR-0003).
- [ ] Regenerate `bdd/collector/live-collector-evidence.md` from the first
      real snapshot (Scenarios B–E), then write the collector spec via `/spec`
      retroactively if it stays.

### Pipeline slice 1 — anchor frame (next)

- [ ] `/spec render-frame` — one PNG from one real PORTAL hour on OSM
      geometry, ribbons by volume; settle the segment↔station width rule there
- [ ] Pull I-205 sensor data (`highway_id=3,4`, same call as §1) — only its
      metadata is sampled

## Open queue (non-blocking)

- (a) Register for ODOT TripCheck API key and WSDOT access code (event
      overlays / WA side)
- (c) Check whether ODOT/PBOT publish a closure-specific dashboard or feed
      mid-closure — second research pass
- (d) Unit tests for the collector's cap-skip and backoff branches (evidence
      "Open gaps")
- (e) `.claude/workflow-config.json` says `spend_tracking: true` with a wired
      adapter, but this repo has no `telemetry/`; either wire it or set false
- (f) Speed-as-color on the freeway ribbons, and 15-min vs hourly cadence —
      decide in the render-frame spec

## Blockers

- Arterial data capture is idle until the two keys land — every day without
  them is a day missing from the arterial layer (freeway data is unaffected;
  PORTAL archives it).
