# STATUS.md

**Last updated:** 2026-09-16 (ADRs drafted; collector deployed; TomTom ruled out on licence)
**Phase:** Phase 0 — research & framing (ADR-0001/0002 drafted, pending acceptance)
**Next bounded packet:** Pipeline slice 1 — the anchor artifact: one rendered PNG frame of I-5/I-405 ribbons on OSM geometry from one real PORTAL hour (ADR-0002), with a spec + BDD via `/spec`
**Current readiness:** READY-FOR-NEXT-PACKET (arterial collector idle until the TriMet AppID lands — see Blockers)

## Recent sessions (rolling, last 5)

- **2026-09-15→16** — `samples+adrs+collector` — Pulled real PORTAL freeway
  data (34 Rose Quarter stations, hourly 09-01→09-14, raw 20 s proven) and
  OSM corridor geometry; confirmed PORTAL has no Portland arterial data.
  Drafted ADR-0001 (geographic ribbon map: freeway volume ribbons + arterial
  speed layer), ADR-0002 (Python frame pipeline) and ADR-0003 (collect before
  the anchor frame). Deployed the live collector on claude-box and hardened it
  across eight architecture-review rounds. Read TomTom's T&C and **removed it**
  — §11.4 forbids storing Results — leaving the arterial layer on the TriMet
  bus proxy alone. Collector is v1.0, 40 tests, idle pending the AppID.
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

- [ ] **Human:** register a TriMet AppID
      (https://developer.trimet.org/appid/registration/) and write
      `TRIMET_APP_ID=...` to `/home/claude/.config/pdxtrafficmonster/env` on
      claude-box, owned by `claude`, mode 600. No restart needed. This is the
      project's only remaining blocker — every day without it is a
      permanently missing day of arterial data.
- [x] TomTom evaluated and **ruled out 2026-09-16** on licence grounds (T&C
      §11.4 prohibits storing Results). Sources deleted from the collector;
      see ADR-0001 amendment and `docs/research/samples/README.md` §4.
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
- (d) Remaining collector test-coverage gaps are recorded in ADR-0003 "Open"
      (round 8 verified the code clean; these are missing tests, not defects)
- (e) `.claude/workflow-config.json` says `spend_tracking: true` with a wired
      adapter, but this repo has no `telemetry/`; either wire it or set false
- (f) Speed-as-color on the freeway ribbons, and 15-min vs hourly cadence —
      decide in the render-frame spec

## Blockers

- Arterial data capture is idle until the TriMet AppID lands — every day
  without it is a day missing from the arterial layer (freeway data is
  unaffected; PORTAL archives it). With TomTom ruled out, the arterial layer
  now has **no second source**: if the bus proxy proves unusable, the layer is
  dropped rather than replaced.
