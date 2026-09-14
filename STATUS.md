# STATUS.md

**Last updated:** 2026-09-14 (repo seeded with workflow kit + data-source research)
**Phase:** Phase 0 — research & framing
**Next bounded packet:** Decide the visualization concept and tech stack (ADR), scoped against the data actually available per `docs/research/i5-closure-data-sources.md`
**Current readiness:** READY-FOR-NEXT-PACKET

## Recent sessions (rolling, last 5)

- **2026-09-14** — `repo-seed` — Created the PDXTrafficMonster repo, installed
  the Claude Code agentic workflow kit (CLAUDE.md, `.claude/`, STATUS/HANDOFF,
  docs/bdd scaffolding), and seeded `docs/research/i5-closure-data-sources.md`
  from a prior research session surveying ODOT/PBOT/WSDOT/PORTAL/TriMet/Waze/
  Google/TomTom as candidate data sources. No code yet.

## Active work

### Decide visualization concept + tech stack

- [ ] Settle on the visualization concept (flow map across I-5/I-405/I-205?
      speed/congestion heatmap over time? before/after split?) — the "monster"
      framing implies an animated, organic flow rather than a static chart
- [ ] Pick a primary data source to anchor on (PORTAL loop-detector data is
      the leading candidate — see research note) and confirm actual field
      names/format by pulling a real sample
- [ ] Choose the rendering stack (static site + D3/Observable Plot vs. a
      Python animation pipeline vs. something else) and record it as an ADR
- [ ] Scope the closure window to cover (2026-09-11 start; ~5 weeks, watch
      for ODOT's actual reopening announcement)

## Open queue (non-blocking)

- (a) Register for ODOT TripCheck API key and WSDOT access code once the
      stack is chosen
- (b) Pull a sample of PORTAL station data near the Rose Quarter to confirm
      format before committing to it as the primary source
- (c) Check whether ODOT/PBOT have published any project-specific dashboard
      or data feed for this closure specifically (beyond TripCheck) as the
      closure progresses — worth a second research pass mid-closure

## Blockers

- None. Visualization concept and stack are open decisions, not blockers.
