# How To Use the Agentic Workflow Kit (Claude Code)

This is the full operating guide. If you just want to get running, the Quick
Start in [README.md](README.md) is enough. This document explains *why* each
piece exists and how to adapt it to your project.

## The mental model

Agentic development fails in predictable ways: lost continuity between sessions,
unbounded scope, "done" claimed without proof, decisions that vanish into chat,
and tests that pass while the real artifact was never checked.

This kit is an operating system that closes each of those gaps:

| Failure | The countermeasure |
|---|---|
| Lost continuity | `STATUS.md` is the single current-state file; `/startup` reads it every session |
| Unbounded scope | Work is sliced into **bounded packets** with a named proof |
| Unproven "done" | Three proof layers: unit tests, BDD evidence, anchor artifact verified on disk |
| Vanishing decisions | Every non-obvious decision is an immutable **ADR** |
| Unchecked artifacts | A slice isn't done until the real artifact is read back off disk |

## Installing into your project

Copy these into the repo you want to operate agentically:

```text
CLAUDE.md                    -> repo root
.claude/                     -> repo root (merge with any existing .claude/)
scripts/continuity_budget.py -> scripts/
templates/STATUS.md          -> STATUS.md
templates/HANDOFF.md         -> HANDOFF.md      (optional — see below)
templates/docs/*             -> docs/
templates/bdd/README.md      -> bdd/README.md
```

If your project already has a `.claude/settings.json`, merge the `SessionStart`
hook and the `permissions.allow` list rather than overwriting.

### Filling in `CLAUDE.md`

`CLAUDE.md` is the contract Claude Code loads every session. Keep it short.

1. **Identity** — one sentence on what the project *is*, plus 2–4 sentences of
   orientation.
2. **Invariants** — the 3–8 load-bearing rules that survive every refactor.
   These are what the `arch-reviewer` subagent checks a diff against, so state
   each so a reviewer can *match a diff against it*, not just nod at it. Cite the
   ADR that explains the "why".
3. **Build & test** — the exact install/build/test/lint commands, plus the
   current test posture if it's non-trivial.
4. **Out of scope** — name what you are deliberately *not* doing, so the agent
   doesn't wander.

### Filling in `STATUS.md`

`STATUS.md` is the heartbeat. `/startup` reads **only** this file to ground a
session, and `/closeout` updates it. Keep it current and short:

- header block: last-updated date, phase, next bounded packet, readiness
- **Recent sessions (rolling, last 5)** — one entry per session, newest first,
  trimmed to five (old sessions live in git history)
- **Active work** — the current packet as checkboxes
- **Open queue** — non-blocking things to pull from when the packet closes
- **Blockers**

## The session loop

### `/startup`

Grounds the session before anything changes:

1. **Drift check** — `git fetch`, check for uncommitted changes and whether the
   branch is behind upstream. A dirty tree stops and asks you (stash / leave /
   commit). A behind branch fast-forwards.
2. **Read `STATUS.md`** — and only `STATUS.md`, unless the work needs more.
3. **Continuity budget check** — the fail-open guard (see below).
4. **Identify the next bounded packet** and **confirm the proof** required to
   close it, before any code changes begin.

The `SessionStart` hook in `.claude/settings.json` also runs a lightweight
drift-check automatically at the very start of every session, so you see repo
state even before typing `/startup`.

### Doing the work

A **bounded packet** is one coherent, shippable unit with a clear proof — not an
open-ended phase. For a feature:

1. `/spec <slug>` scaffolds a spec (`docs/specs/<slug>.md`) and a paired BDD
   (`bdd/<feature>/<slug>-bdd.md`). The BDD defines what success looks like
   *before* implementation.
2. Build the **anchor artifact** first — the simplest concrete observable
   version of the thing — then supporting code and unit tests.
3. Produce an **evidence file** (`bdd/<feature>/<slug>-evidence.md`) with raw
   outputs for each scenario.

### Review passes

Two subagents, each with isolated context:

- **`arch-reviewer`** — run before completing a non-trivial change. It reads the
  diff against `CLAUDE.md`'s invariants with fresh context, so it isn't anchored
  by the rationalizations built up while implementing. Invoke it explicitly
  ("use the arch-reviewer subagent on this diff") or let Claude Code delegate.
- **`bdd-evidence-reviewer`** — run after a test run on a feature with BDD
  scenarios. It confirms each scenario was *honestly* hit — raw output present,
  Given/When/Then faithfully represented — not just claimed-as-passing.

### `/closeout`

Leaves the repo clean for next time:

1. Confirm what changed; verify the changed files match the session narrative.
2. Run the BDD-evidence review if a feature landed.
3. Update `STATUS.md` — roll the session log (trim to 5), tick checkboxes,
   update blockers. Trim any file the continuity guard flagged.
4. Sync doc indexes (ADR draft→accepted, new specs/research listed).
5. Stage specific files and commit (never `git add -A`). `[ADR-NNNN]` /
   `[spec:<feature>]` prefixes where they apply.
6. **Ask before pushing** — default is commit-only.

## Decisions and research

- **`/adr <slug>`** — scaffolds an auto-numbered Architecture Decision Record.
  ADRs are immutable once accepted; to change a decision, write a *new* ADR that
  supersedes the old one. One decision per file.
- **`/research <slug>`** — scaffolds a research note: open questions, options,
  and tradeoffs kept out of chat history. When the thinking stabilizes, promote
  it to a spec or ADR.

## Optional features (`.claude/workflow-config.json`)

### Continuity tracking (on by default)

The continuity-tier is everything Claude Code loads at cold start — `CLAUDE.md`,
`STATUS.md`, `HANDOFF.md`, `ROADMAP.md`. Left unchecked these files bloat, and
every session pays the cost. `scripts/continuity_budget.py` measures each file
against a per-file token budget (`.claude/continuity-budget.json`) and warns —
one `CONTINUITY BLOAT:` line — when a file is over.

```bash
python3 scripts/continuity_budget.py           # human-readable table
python3 scripts/continuity_budget.py --check    # quiet unless over budget
python3 scripts/continuity_budget.py --snapshot # append a size row to the trend ledger
```

It is **fail-open**: read-only, always exits 0, never truncates a file or blocks
a session. `/startup` surfaces the warning; the next `/closeout` trims the
flagged file (keep `STATUS.md`'s rolling-5, prune stale `HANDOFF`/`ROADMAP`
entries). That social loop — warn at startup, trim at closeout — is the whole
mechanism. The token estimate uses a `ceil(chars/4)` heuristic times a
Claude-BPE calibration (~1.7); no tokenizer is a runtime dependency.

To disable it, set `"continuity_tracking": false` and remove the guard from the
`SessionStart` hook.

### Spend tracking (off by default)

Claude Code has a built-in **`/cost`** command that reports the current
session's token and dollar usage — that is the spend readout this kit relies on.
The `spend_tracking` flag exists for teams that wire their own cross-repo spend
adapter (e.g. a shared ledger across every repo a developer works in); v1 of
this kit ships no such adapter, so the flag is off and `/startup`/`/closeout`
defer to `/cost`.

## The single-repo vs. paired-repo choice

`HANDOFF.md` and `ROADMAP.md` are optional. A single-repo project can run on
`STATUS.md` alone. Keep `HANDOFF.md` when you want a slow-changing orientation
doc for whoever picks the project up next, and `ROADMAP.md` when strategic
direction needs its own home. The continuity guard budgets all four but only
flags files that actually exist.

## Adapting the kit

- **Different BDD style?** Gherkin `.feature` files work fine — the
  `bdd-evidence-reviewer` cares about honest evidence, not the file format.
- **Different invariants?** That's the point — the invariants in `CLAUDE.md` are
  yours to write. The review pass is generic; the rules are project-specific.
- **Different commands?** `.claude/commands/*.md` are plain Markdown. Edit them,
  or add your own.

The kit is small on purpose. Every piece is legible and portable, and a human
can follow the whole workflow without any agent at all.
