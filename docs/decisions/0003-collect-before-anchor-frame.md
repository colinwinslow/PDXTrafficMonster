---
id: 0003
title: Live-only sources are collected before the anchor frame — a bounded exception to anchor-artifact discipline
status: draft
date: 2026-09-16
supersedes: []
superseded-by: null
tags: [process, data, collector, scope]
---

# ADR-0003: Live-only sources are collected before the anchor frame

## Context

`CLAUDE.md` requires the simplest observable artifact first — for this
project, one rendered frame (ADR-0001). The arterial layer in ADR-0001 rests
on two sources with no public history: TriMet GTFS-realtime and TomTom
Traffic Flow. Data from those sources exists only if something is recording
it at the time; a frame rendered next week cannot include a day nobody
captured. So on 2026-09-15 a collector daemon, systemd unit, installer, and
tests were built and deployed *before* any frame existed — plumbing before
the visible thing, which the discipline forbids. The fresh-context
architecture review flagged that the exception was justified in a commit
message but never recorded as a decision.

## Decision

**Sources whose data is unrecoverable if not captured live may be collected
ahead of the anchor artifact, under three conditions: the collector stores
raw responses with provenance (URL, status, sha256, timestamp); it is gated
per source on the same invariants as the visualization (a source whose
terms are unread is disabled, not archived-and-hoped); and the exception is
bounded to collection — no pipeline, rendering, or analysis code is written
ahead of the anchor frame.** Everything else in this repo still starts with
the artifact.

## Rationale

- The anchor-artifact rule exists to stop plumbing from substituting for
  something real. Here the plumbing *is* what makes the later real thing
  possible; skipping it doesn't produce a frame sooner, it produces a frame
  with a hole in it.
- Raw-bytes storage keeps the exception honest: nothing is interpreted early,
  so no design is locked in by the collector.
- The TomTom gate (`PDXTM_TOMTOM_ENABLED`, default off) is the concrete form
  of "same invariants as the visualization": invariant 2 is checked before
  the archive exists, not after.
- Static GTFS is snapshotted weekly alongside the realtime feed because a
  bus speed between two stops is only traceable (invariant 1) against the
  `stops`/`trips`/`shapes` of the feed version that was live when it was
  recorded.

## Consequences

**Enables:**
- Arterial capture from 2026-09-15 (TriMet, once the AppID lands; static
  GTFS immediately) instead of from whenever the pipeline exists.

**Constrains:**
- Retention: raw snapshots are kept for the life of the project (est. 2–5 GB
  through reopening on a 27 GB volume); the collector stops fetching below
  1 GiB free rather than deleting anything. Pruning is a human decision.
- The collector runs from an installed copy (`/usr/local/lib/…`), not the
  worktree, so branch checkouts can't change what's running; redeploy is
  `scripts/install_collector.sh`.
- The exception does not extend to a "quick" decoder, dashboard, or
  aggregation job — those wait for the frame.

**Open:**
- Nothing alerts on a stale heartbeat; failures that keep the process alive
  are found by looking (`status.json`). Cheap to add via a timer if the
  closure runs long.
- The restored-schedule clamp is weakest exactly where loss is most
  expensive: for `trimet_static` it resolves to the 7-day interval itself, so
  a clock-ahead epoch is "clamped" to a full week's park — one missed feed
  version, which by this ADR's own reasoning is unrecoverable. Accepted for
  now because a spurious weekly re-pull is 29.5 MB and the failure needs a
  clock anomaly to trigger; revisit if a feed version is ever actually missed.
- The collector's spec is retroactive (STATUS.md, "Live arterial collection").

## References

- ADR-0001 (arterial layer, TomTom terms "Open"), ADR-0002
- `CLAUDE.md` — "Anchor-artifact discipline"
- `scripts/collect_live.py`, `bdd/collector/live-collector-bdd.md`
