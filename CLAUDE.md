# CLAUDE.md — PDXTrafficMonster Agent Contract

## Identity

PDXTrafficMonster is an animated data visualization showing how Portland traffic
redirects during the five-week closure of I-5 southbound through the Rose
Quarter (closed nightly/all-day starting 2026-09-11, ODOT's I-5 Rose Quarter
Improvement Project, expected to reopen mid-October 2026).

The goal is to turn real public traffic-sensor and incident data into an
animated view of how drivers reroute across I-5, I-405, I-205, and the local
street grid as the closure diverts flow — not a synthetic simulation. The
concrete visualization design (flow map, heatmap, before/after comparison,
etc.) and tech stack are not yet decided; that is the first bounded packet.

This project is developed **agentically**. The human provides direction and
oversight; the agent does the implementation. Work is reviewed by reading
commits, decision records (ADRs), specs, and the inspectable evidence that
tests produce.

## Session start: read this only

On session start, run `/startup`. The required read set is **`STATUS.md` only**
— it is the single source for current phase, current bounded packet, and the
rolling session log.

Do not load other docs unless the work requires them. The doc map below tells
you when to load what.

## Doc map

| Question | Read |
|---|---|
| What's the current state of the project? | `STATUS.md` |
| What data sources exist and why were they chosen (or rejected)? | `docs/research/i5-closure-data-sources.md` |
| What is this project, architecturally? | `docs/architecture/pdxtrafficmonster-architecture.md` (once it exists) |
| Why did we decide X? | `docs/decisions/NNNN-*.md` (one ADR per decision) |
| What does feature Y do? | `docs/specs/<feature>.md` (one spec per shippable feature) |
| What are the scenarios for feature Y? | `bdd/<feature>/<slug>-bdd.md` |
| Is Z still an open question? | `docs/research/<topic>.md` |
| Who picks this up next / durable orientation? | `HANDOFF.md` |
| How does the project build/test? | This file, "Build & test" |
| What session commands exist? | `.claude/commands/` (this repo's `/startup`, `/closeout`, etc.) |
| Are optional workflow features enabled? | `.claude/workflow-config.json` |

If the question doesn't fit the table, ask. Don't guess.

## Invariants (load-bearing; do not violate)

1. **Provenance over synthesis** — every number the visualization displays
   must trace back to a named public data source (PORTAL, ODOT TripCheck,
   WSDOT, PBOT/PortlandMaps, TriMet, TomTom Traffic Index). No estimated,
   interpolated-as-if-real, or placeholder data presented as measured without
   a visible caveat. (see `docs/research/i5-closure-data-sources.md`)
2. **Public-access data only** — no data source that requires a signed
   partnership agreement whose terms forbid redistribution (e.g. Waze
   Connected Citizens Program) and no scraping of a source in violation of
   its terms of service (e.g. Google Maps traffic tiles). If this changes,
   it needs an ADR explaining the new terms and why they're compatible with
   a public repo.
3. More invariants (visualization framework, data pipeline shape, update
   cadence) get written once the stack is chosen — see ADR to come out of the
   first bounded packet.

For the deep "why" behind each, see the cited ADRs.

## Workflow

### BDD before implementation

Every implementation slice begins with a small, inspectable BDD that defines
the artifact proving success. Tests derive from the BDD; code makes the tests
pass. Scaffold a spec + paired BDD with `/spec <slug>`.

### Three layers of correctness proof

| Layer | Owns | When | Format |
|---|---|---|---|
| **Unit tests (red/green TDD)** | Failure paths, edge cases, regression net | Every code change; failing tests block commit | test runner output |
| **BDD evidence** | User-facing happy path + catastrophic/irreversible failures | After feature work; human reviews | Markdown evidence file referenced from the BDD |
| **Anchor artifact** | The simplest concrete observable version of the thing | Built first, before supporting code | Whatever the feature *is* (a rendered frame, a data file, a chart) |

### Verify on disk

A slice is not done until the real artifact has been verified on disk (read the
changed files back; confirm the expected content is present). "Tests pass" is
necessary but not sufficient.

### Anchor-artifact discipline

Build the simplest concrete observable version of the thing **first**, before
supporting infrastructure. If you're building plumbing before anything visible
exists, stop and reorder.

## Session commands

Native Claude Code slash commands, defined in `.claude/commands/`:

| Command | Purpose |
|---|---|
| `/startup` | Drift-check + read STATUS + identify next bounded packet + confirm proof |
| `/closeout` | Update STATUS rolling log + sync doc indexes + run BDD-evidence review + commit |
| `/adr <slug>` | Scaffold a new ADR with auto-numbering |
| `/spec <slug>` | Scaffold a new spec + paired BDD |
| `/research <slug>` | Scaffold a new research note |

## Review passes

Subagents in `.claude/agents/`, each run in isolated context:

| Review | Subagent | When |
|---|---|---|
| Architecture review | `arch-reviewer` | Before completing a non-trivial implementation — a fresh, un-anchored read of the diff against the invariants |
| BDD-evidence review | `bdd-evidence-reviewer` | After a test run on a feature with BDD scenarios (run at `/closeout`) |

## Build & test

No code yet. The first bounded packet decides the visualization approach and
tech stack (candidates: a static site with D3/Observable Plot fed by a Python
or Node data-pull script; framework TBD by ADR) and this section gets filled
in behind that ADR.

## Commit norms

- One commit per coherent change. Messages describe **why**, not just what.
- ADR commits: `[ADR-NNNN]` prefix. Spec commits: `[spec:<feature>]` prefix.
- Never skip hooks (`--no-verify`) unless the user explicitly asks. If a hook
  fails, fix the underlying issue and create a NEW commit; do not amend.
- Stage specific files. Never blanket `git add -A` / `git add .`.
- Ask before pushing. Default is commit-only.

## What is out of scope (now)

- Waze data (partnership-gated, non-redistributable — see invariant 2).
- Scraping Google Maps traffic tiles (ToS violation — see invariant 2).
- Live/real-time serving infrastructure. First cut is a post-hoc animated
  visualization of the closure window, not a live dashboard.

## When in doubt

Ask the human. Direction is the human's call; implementation details are yours.
If a spec is ambiguous, surface the ambiguity in chat and write the resolution
into the spec before coding.
