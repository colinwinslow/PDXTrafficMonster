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
on sources with no public history: TriMet GTFS-realtime, and at the time this
was written TomTom Traffic Flow (since removed — ADR-0001 amendment). Data from
such sources exists only if something is recording
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
- The per-source gate is the concrete form of "same invariants as the
  visualization": invariant 2 is checked before the archive exists, not after.
  **This paid for itself on 2026-09-16.** TomTom shipped gated off pending its
  T&C; when the terms were read they turned out to prohibit storing Results
  entirely (ADR-0001 amendment). Because the gate defaulted closed, not one
  prohibited byte was ever written — the sources were deleted having collected
  nothing. Had the default been "archive and ask later", the remedy would have
  been deleting an unlawful archive instead of deleting dead code.
- Static GTFS is snapshotted weekly alongside the realtime feed because a
  bus speed between two stops is only traceable (invariant 1) against the
  `stops`/`trips`/`shapes` of the feed version that was live when it was
  recorded.

## Consequences

**Enables:**
- Arterial capture from 2026-09-15 (TriMet, once the AppID lands; static
  GTFS immediately) instead of from whenever the pipeline exists.

**Constrains:**
- A source whose licence is unread does not collect. That is a real cost —
  TomTom's gate meant no probe data exists for 2026-09-15/16, which would have
  been usable had the terms permitted it — and it is the right trade, because
  the alternative risks an archive that must be destroyed.
- Retention: raw snapshots are kept for the life of the project (est. 2–5 GB
  through reopening on a 27 GB volume); the collector stops fetching below
  1 GiB free rather than deleting anything. Pruning is a human decision.
- The collector runs from an installed copy (`/usr/local/lib/…`), not the
  worktree, so branch checkouts can't change what's running; redeploy is
  `scripts/install_collector.sh`.
- The exception does not extend to a "quick" decoder, dashboard, or
  aggregation job — those wait for the frame.

**Open:**

*Deferred deliberately.* Eight architecture-review rounds ran against the
collector. Round 8 verified the code CLEAN — 20 real-socket paths through
`fetch()`, 60 mutations with null controls, no correctness, data-integrity or
silent-stop defect — and the loop was stopped there. What remains below is
**missing test coverage over correct code**, plus small honesty gaps. It is
recorded rather than fixed because the project's actual blocker is the TriMet
AppID, not collector robustness, and because each additional round has been
returning findings of lower severity than the last.

*(Items that applied only to the TomTom sources — daily-cap coverage, the 429
cross-style break, charge-before-fetch — were dropped on 2026-09-16 with those
sources. The rest still stand.)*

- **Unpinned-but-correct guards** (a mutation survives the suite): `_fetch`'s
  `deadline=DEADLINE[source]` wiring; `urlopen(timeout=...)`; the error path's
  inner `except (OSError, ValueError, HTTPException)` — i.e. the round-5 escape
  itself has no regression test; `ok = status == 200 and len(body) > 0`, so an
  empty 200 stored as a real capture is unpinned.
- **Sibling gaps in the tests** (not the code): backoff's effect on `next_due`
  is asserted for `trimet` only. The code is correct for both sources.
- **A truncated error body is reported with its short length unmarked**, while
  a *capped* one is marked `(limit-truncated)` — the same argument as the cap
  marker, applied to one sibling and not the other.
- `urllib.request.Request()` sits outside `fetch()`'s `try`; unreachable today
  because every URL is an https module constant.
- `(limit-truncated)` is written bare when a server sends no `Content-Type`.
- `warn_hourly` has no cap on distinct keys.
- Nothing alerts on a stale heartbeat; failures that keep the process alive
  are found by looking (`status.json`). Cheap to add via a timer if the
  closure runs long.
- **Truncation is undetectable for close-delimited bodies.** The collector
  rejects a short response by comparing delivered bytes against the declared
  `Content-Length` (and catches `IncompleteRead` for chunked). An HTTP/1.0 or
  `Connection: close` body declares neither, so a truncated one would be
  archived as complete. Every endpoint this collector fetches serves
  `Content-Length` or chunked (verified for `developer.trimet.org`), so the
  gap is currently unreachable — but it is a gap, not a guarantee.
- **`fetched_at` is cycle start, not per-request time.** Handlers run
  sequentially within one cycle, so a snapshot taken after a slow download can
  carry a timestamp — and a UTC day-partition directory — up to ~15 min early.
  Harmless at the closure's hourly/daily granularity; would need fixing before
  anything reasons about sub-minute timing or a midnight boundary.
- The restored-schedule clamp is weakest exactly where loss is most
  expensive: for `trimet_static` it resolves to the 7-day interval itself, so
  a clock-ahead epoch is "clamped" to a full week's park — one missed feed
  version, which by this ADR's own reasoning is unrecoverable. Accepted for
  now because a spurious weekly re-pull is 29.5 MB and the failure needs a
  clock anomaly to trigger; revisit if a feed version is ever actually missed.
- The collector's spec is retroactive (STATUS.md, "Live arterial collection").

## References

- ADR-0001 (arterial layer; amended 2026-09-16 to drop TomTom), ADR-0002
- `CLAUDE.md` — "Anchor-artifact discipline"
- `scripts/collect_live.py`, `bdd/collector/live-collector-bdd.md`
