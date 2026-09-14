# Specs

One spec per shippable feature: `docs/specs/<slug>.md`, paired with a BDD file
at `bdd/<feature>/<slug>-bdd.md`. Scaffold both with `/spec <slug>`.

## What a spec is

A spec defines the **contract surface** of a feature: the observable behavior,
the public interface, the anchor artifact, the proof requirements. It is the
thing implementation makes true. It is NOT a design doc or a tutorial.

## Lifecycle

- Specs are authored as `status: draft`.
- A `draft` is promoted to `accepted` once the contract is agreed.
- Accepted specs are **immutable**. Supersede by writing a new spec.

## Spec / BDD split

The spec lives here; its scenarios live in `bdd/<feature>/<slug>-bdd.md`. The
spec links to the BDD; the BDD enumerates Given/When/Then scenarios; the
implementing slice produces an evidence file proving each scenario was hit.

## Current specs

- `<slug>` — `<title>` (draft)
