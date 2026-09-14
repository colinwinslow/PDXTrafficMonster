---
description: End a session cleanly — update STATUS.md, verify artifacts on disk, commit. Don't push without asking.
---

End a work session. Leave the repo clean and understandable for the next
session. **Don't push without asking.**

## Steps

1. **Confirm what changed this session.** `git status` and `git diff --stat`.

2. **Verify changed files match the session work.** Read back the changed
   files. If files changed that don't fit the session narrative, surface to the
   user before committing.

3. **If a feature with BDD scenarios was implemented, run the BDD-evidence
   review pass.** Invoke the `bdd-evidence-reviewer` subagent (or run the review
   inline) and confirm each scenario was honestly hit with raw evidence — not
   just claimed-as-passing.

4. **Update `STATUS.md`:**
   - Update the `Last updated:` date.
   - Update `Phase`, `Next bounded packet`, `Current readiness` if changed.
   - Tick `Active work` checkboxes for any packets that closed.
   - Add a new entry to the **"Recent sessions (rolling, last 5)"** log at the
     top: date, packet name, 1–3 sentences on what closed/changed.
   - **Trim the oldest entry if the section now exceeds 5.** Old sessions live
     in git history; do not preserve them here.
   - Update `Blockers` if any landed or cleared.
   - **Continuity budget (when `continuity_tracking` is enabled).** If this
     session's `/startup` surfaced a `CONTINUITY BLOAT:` warning — or to check
     now — run `python3 scripts/continuity_budget.py --check`. For each file it
     flags, trim it back under budget as part of this closeout: enforce
     `STATUS.md`'s rolling-5, and prune stale `HANDOFF.md` / `ROADMAP.md` entries
     (old detail lives in git history). Re-run `--check` and confirm it is silent
     before committing. This is the discipline the guard exists to keep honest.

5. **Sync doc indexes if any status changed this session:**
   - ADR `draft` → `accepted`: update `docs/decisions/README.md` per its
     index-label convention.
   - New spec/research note: confirm it's listed in the relevant README.

6. **Stage and commit.** Stage specific files — never blanket `git add -A`. Use
   a HEREDOC for the message. Conventions per `CLAUDE.md`:
   - `[ADR-NNNN]` prefix for ADR commits
   - `[spec:<feature>]` prefix for spec commits
   - Why, not just what

7. **Confirm `git status` is clean** after the commit.

8. **Ask before pushing.** Default is commit-only. If the user confirms,
   `git push origin <branch>`.

9. **Optional spend footer.** When `spend_tracking` is enabled, close with a
   spend line — Claude Code's built-in `/cost`, or your custom cross-repo spend
   adapter's gauge if you have wired one. <!-- telemetry add-on: this repo has
   wired one; the gauge commands are in `telemetry/README.md`. Note step 0 —
   `mark-closeout` must run FIRST for the footer's timing to be accurate. -->

## Slice-closing completion report (in the commit body)

When a slice closes, the commit body includes:

- **Completed slice** — name/number
- **What it does** — goal + sub-steps in plain language
- **Tests run** — exact commands
- **What each test proves** — one line per test/group
- **BDD verification** — scenario, input, expected, observed
- **Artifact verification** — files the user can inspect on disk
- **Open gaps** — any mismatch between implementation, tests, and BDD
- **Next slice** — the next bounded step

Brief commits (doc tweaks, dependency bumps) skip the report.

## Rules

- Never `--no-verify` or skip hooks unless the user explicitly asks.
- Never amend a commit; create a new one if follow-up is needed.
- If a pre-commit hook fails, fix the underlying issue and create a new commit.
- Do not run `git add -A` or `git add .` blindly. Stage specific files.
- A slice is not complete until the real artifact has been verified on disk.
