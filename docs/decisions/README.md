# Architecture Decision Records

One file per decision: `NNNN-<slug>.md`, zero-padded, monotonic. Scaffold with
`/adr <slug>`.

## Lifecycle

- ADRs are authored as `status: draft`.
- A `draft` is promoted to `accepted` once the decision is made (and usually
  once an implementation slice lands behind it). Promotion happens at
  `/closeout`.
- Accepted ADRs are **immutable**. To change a decision, write a NEW ADR that
  names the old one in its `supersedes:` frontmatter and set the old one's
  `superseded-by:`. Never edit an accepted decision in place.

## Index-label convention

In the list below, `accepted` is the silent default (no label). Other states
carry a label:

- `(draft)` — not yet accepted
- `(deprecated YYYY-MM-DD)` — withdrawn
- `(superseded by NNNN)` — replaced by a later ADR

Keep this list in sync at `/closeout` whenever an ADR's status changes.

## Current ADRs

- 0001 — Visualization concept: animated geographic ribbon flow map; freeway volume ribbons + live arterial congestion layer (draft)
- 0002 — Rendering stack: Python frame pipeline (GeoPandas + matplotlib → PNG → ffmpeg) (draft)
<!-- Add new ADRs in numeric position. Sub-numbered amendments (e.g. 0001a) go
     immediately after their parent. -->
