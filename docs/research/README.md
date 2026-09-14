# Research Notes

Exploratory scratch space: `docs/research/<slug>.md`. Scaffold with
`/research <slug>`.

## What a research note is

A place to think before committing to a decision or a contract. Research notes
are **not load-bearing** — they may or may not promote to a spec or ADR.

## Lifecycle

- Authored as `status: open`.
- When the thinking stabilizes, **promote**: write a spec (`/spec`) or an ADR
  (`/adr`), then update the note's `Resolution` section and flip `status` to
  `promoted-to-spec`, `promoted-to-adr`, or `abandoned`.
- A note that's been `open` for a long time with no movement is a signal —
  either the question doesn't matter, or it's blocked on something.

## Current research notes

- `i5-closure-data-sources` — Public data sources for the I-5 southbound
  Rose Quarter closure (open)
