# Claude Code ↔ Codex: Construct Mapping

This kit is the **Claude Code** edition of the Agentic Workflow Kit. The same
workflow exists as the
[`agentic-workflow-kit`](https://github.com/KagwerksEngineering/agentic-workflow-kit)
repo, re-expressed for **Codex** and the VS Code Codex extension. The workflow
originated in Claude Code — this edition uses its native constructs directly;
the Codex edition re-expresses them as documented protocols because Codex has a
leaner harness.

Here's the correspondence, so you can move a project between the two.

## The table

| This kit (Claude Code) | Codex edition | Why they differ |
|---|---|---|
| **`CLAUDE.md`** (project instructions) | `AGENTS.md` | Claude Code auto-loads `CLAUDE.md`; Codex auto-loads `AGENTS.md` (the [agents.md](https://agents.md) standard — note the plural). Same contract, different filename. |
| **`.claude/commands/*.md`** (native slash commands) | `codex/*.md` protocol docs | Claude Code runs a `.md` file in `.claude/commands/` as a first-class slash command. Codex has no equivalent, so it declares in `AGENTS.md` "when the user types `/startup`, follow `codex/startup.md`" — a documented procedure, not a native command. |
| **`.claude/agents/*.md`** (subagents, isolated context) | `codex/review-*.md` review passes | Claude Code spawns subagents with their own fresh context — ideal for an un-anchored architecture review. Codex has no subagents, so the review runs as a standalone `codex exec` (fresh context ≈ the isolation a subagent gave you). |
| **`.claude/settings.json` `SessionStart` hook** (auto drift-check) | inline git commands in `codex/startup.md` | Claude Code fires a lifecycle hook at session start; the kit uses it for a fail-open git drift-check. Codex has no lifecycle-hook parity, so the drift-check is written into the `/startup` protocol as explicit git commands. |
| **`.claude/settings.json` permissions allowlist** | Codex approval modes | Claude Code governs tool approval with a per-pattern allowlist. Codex governs it through run modes (read-only / auto-edit / full-access). Configure to taste; the workflow doesn't depend on either. |
| **`.claude/workflow-config.json`** (feature flags) | `codex/workflow-config.json` | Same idea, same file, different directory. |
| **`scripts/continuity_budget.py`** (continuity guard) | `scripts/codex_continuity.py` | The same fail-open continuity-tier budget guard. Both are stdlib Python 3; the Claude Code edition uses a Claude-BPE token calibration (~1.7), the Codex edition an OpenAI o200k_base calibration (~1.06). |
| Claude Code native `/cost` | `scripts/codex_spend.py` (cross-repo spend gauge) | Claude Code has a built-in `/cost` readout. The Codex edition ships a Python spend gauge + cross-repo ledger because Codex has no built-in equivalent. This kit gates spend tracking off by default and defers to `/cost`. |
| MCP servers | Codex MCP via `~/.codex/config.toml` | Both support MCP. Optional — not part of this core workflow. |

## The one principle to keep

Claude Code automates more; Codex automates less. The workflow is the same
either way: **start grounded, ship one bounded packet, verify with evidence,
record durable decisions, close cleanly.** Whether a step is a native command,
a subagent, a hook, or a readable protocol file is an implementation detail of
the harness — the discipline is portable, and a human can follow it without any
agent at all.
