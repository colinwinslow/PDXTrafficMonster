#!/usr/bin/env python3
"""Continuity-tier token-budget guard for the Claude Code agentic-workflow-kit.

It measures the always-loaded continuity files an agent ingests at cold start --
the installed repo's live root ``CLAUDE.md`` / ``STATUS.md`` / ``HANDOFF.md`` /
``ROADMAP.md`` -- against a per-file token budget, and warns (fail-open) when one
is over.

Three legs:
1. A measured per-file token budget (``.claude/continuity-budget.json``).
2. A fail-open warn -- one loud line per over-budget file (``--check``).
3. A social loop: the warn surfaces at ``/startup``; the next session trims the
   file at ``/closeout``. The ``templates/STATUS.md`` "Recent sessions (rolling,
   last 5)" convention is the target behavior; this guard keeps it honest.

It is NOT a hard cap. Nothing truncates a file or blocks startup/commit.

Token model: a deterministic ``ceil(chars/4)`` heuristic (what the guard
enforces) times a CALIBRATION constant for a real-token estimate. The default
calibration (~1.7) tracks Claude's BPE tokenizer; no tokenizer is a runtime
dependency (stdlib only, keeps any install clean).

Usage::

    python3 scripts/continuity_budget.py            # human-readable table
    python3 scripts/continuity_budget.py --check     # quiet unless over budget
    python3 scripts/continuity_budget.py --snapshot  # append a size row to the ledger

Read-only and ALWAYS exits 0. Any error degrades to one line + exit 0, so it is
safe to wire into ``/startup`` and the SessionStart hook -- it can never block a
session.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET_CONFIG = ROOT_DIR / ".claude" / "continuity-budget.json"
CHECK_CMD = "python3 scripts/continuity_budget.py"
SNAPSHOT_SCHEMA = "claude-continuity-snapshot/v1"

# real/heuristic for Claude's BPE tokenizer (~1.7). Claude's tokenizer is less
# dense than OpenAI's o200k_base (whose calibration is ~1.06) -- do NOT reuse
# that value here.
DEFAULT_CALIBRATION = 1.7

# Continuity-tier files checked at the installed repo's live root, in load order.
CONTINUITY_FILES = ("CLAUDE.md", "STATUS.md", "HANDOFF.md", "ROADMAP.md")


# -- pure helpers (no I/O; the tests hit these directly) ----------------------

def heuristic_tokens(text: str) -> int:
    """Deterministic ceil(chars/4). Empty/whitespace -> 0."""
    stripped = str(text).strip()
    return 0 if not stripped else math.ceil(len(stripped) / 4)


def real_tokens(text: str, calibration: float = DEFAULT_CALIBRATION) -> int:
    """Calibrated real-token estimate (heuristic x calibration)."""
    return round(heuristic_tokens(text) * calibration)


def is_over(text: str, budget: int | None, calibration: float = DEFAULT_CALIBRATION) -> bool:
    """True iff the real-token estimate exceeds the budget (None budget = never over)."""
    return budget is not None and real_tokens(text, calibration) > budget


def fmt(n: float) -> str:
    return f"{int(n):,}"


def bloat_line(label: str, real: int, budget: int, cmd: str = CHECK_CMD) -> str:
    """The single loud warn line emitted per over-budget file in --check mode."""
    return (f"CONTINUITY BLOAT: {label} ~{fmt(real)} real-tok > {fmt(budget)} budget"
            f" -- trim at closeout; run '{cmd}'")


# -- config -------------------------------------------------------------------

def load_budget_config(path: Path = DEFAULT_BUDGET_CONFIG) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    calibration = data.get("calibration")
    if not isinstance(calibration, (int, float)) or calibration <= 0:
        calibration = DEFAULT_CALIBRATION
    budgets = data.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    return {"calibration": float(calibration), "budgets": budgets}


# -- snapshot ledger (accumulate size data now; trend/cost report later) ------
# One JSONL row per /startup, in a shared per-user dir above all repos, so a
# team's continuity-tier size accumulates cross-repo from day one. Reading it (a
# regrowth trend) is a later, purely additive step -- this only collects. Never
# blocks: any write error is swallowed and we exit 0.

def snapshot_dir() -> Path:
    """Shared per-user dir above all repos."""
    override = os.environ.get("AWK_CLAUDE_DIR") or os.environ.get("CONTINUITY_SNAPSHOT_DIR")
    return Path(override).expanduser() if override else Path.home() / ".agentic-workflow-kit-claude"


def snapshot_path() -> Path:
    return snapshot_dir() / "continuity-snapshots.jsonl"


def snapshot_row(rows: list[dict[str, Any]], repo: str, ts: float) -> dict[str, Any]:
    """Pure: build one snapshot row from measured rows (present files only)."""
    by_file = {r["label"]: r["real"] for r in rows if not r["missing"]}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "ts": int(ts),
        "repo": repo,
        "total_real": sum(by_file.values()),
        "by_file": by_file,
    }


def cmd_snapshot(rows: list[dict[str, Any]], repo: str) -> int:
    """Append one snapshot row to the shared JSONL. Never raises; always 0."""
    try:
        path = snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        row = snapshot_row(rows, repo, time.time())
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        pass  # never block a session
    return 0


# -- measurement over the live root files -------------------------------------

def measure(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    calibration = config["calibration"]
    budgets = config["budgets"]
    rows: list[dict[str, Any]] = []
    for name in CONTINUITY_FILES:
        budget = budgets.get(name)
        path = root / name
        if not path.exists():
            rows.append({"label": name, "missing": True, "budget": budget})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            rows.append({"label": name, "missing": True, "budget": budget})
            continue
        heur = heuristic_tokens(text)
        real = real_tokens(text, calibration)
        rows.append({
            "label": name, "missing": False,
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n") + 1,
            "heur": heur, "real": real, "budget": budget,
            "over": is_over(text, budget, calibration),
        })
    return rows


# -- commands -----------------------------------------------------------------

def cmd_check(rows: list[dict[str, Any]]) -> int:
    """Quiet unless something is over budget; ALWAYS exit 0."""
    for r in rows:
        if not r["missing"] and r.get("over"):
            print(bloat_line(r["label"], r["real"], r["budget"]))
    return 0


def cmd_report(rows: list[dict[str, Any]], config: dict[str, Any]) -> int:
    calibration = config["calibration"]
    print("\nContinuity-tier budget (always-loaded at cold-start)\n")
    print(f"  {'file':16}{'KB':>7}{'lines':>8}{'heur-tok':>10}{'real-tok~':>11}{'budget':>9}   flag")
    print("  " + "-" * 66)
    total_real = 0
    any_over = False
    for r in rows:
        if r["missing"]:
            budget = "-" if r.get("budget") is None else fmt(r["budget"])
            print(f"  {r['label']:16}{'(absent)':>7}{'':>8}{'':>10}{'':>11}{budget:>9}")
            continue
        total_real += r["real"]
        if r["budget"] is None:
            flag = ""
        elif r["over"]:
            flag = f"OVER {fmt(r['real'] - r['budget'])}"
            any_over = True
        else:
            flag = "ok"
        budget = "-" if r["budget"] is None else fmt(r["budget"])
        print(f"  {r['label']:16}{r['bytes'] / 1024:7.0f}{fmt(r['lines']):>8}"
              f"{fmt(r['heur']):>10}{fmt(r['real']):>11}{budget:>9}   {flag}")
    print("  " + "-" * 66)
    print(f"  {'TOTAL real-tok~':16}{'':>7}{'':>8}{'':>10}{fmt(total_real):>11}")
    print(f"\n  real-tok~ = heuristic(ceil chars/4) x {calibration} "
          f"(Claude BPE calibration).")
    if any_over:
        print("  Over-budget files: trim at closeout (keep STATUS's rolling-5, "
              "prune stale HANDOFF/ROADMAP entries).")
    print("")
    return 0


# -- CLI ----------------------------------------------------------------------

def _force_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuity-tier token-budget guard (fail-open).")
    parser.add_argument("--check", action="store_true",
                        help="Quiet unless a file is over budget; print one BLOAT line each. Always exit 0.")
    parser.add_argument("--snapshot", action="store_true",
                        help="Append one continuity-size row to the shared JSONL ledger (accumulates trend data). Always exit 0.")
    parser.add_argument("--root", type=Path, default=ROOT_DIR,
                        help="Repo root whose live continuity files are checked (default: this repo).")
    parser.add_argument("--budget-config", type=Path, default=DEFAULT_BUDGET_CONFIG,
                        help="Budget/calibration JSON (default: .claude/continuity-budget.json).")
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)
    config = load_budget_config(args.budget_config)
    rows = measure(args.root, config)
    if args.snapshot:
        cmd_snapshot(rows, Path(args.root).resolve().name)
    if args.check:
        return cmd_check(rows)
    if args.snapshot:
        return 0  # snapshot-only: collect quietly, no table
    return cmd_report(rows, config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # never block a session
        print(f"  continuity guard unavailable ({exc})")
        raise SystemExit(0)
