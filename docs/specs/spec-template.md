---
status: draft
date: YYYY-MM-DD
depends-on-adrs: []
---

# <Feature>: <Short title>

## Status

Draft. Defines the contract surface for <feature> per <relevant ADR>.

## Related docs

- [bdd/<feature>/<slug>-bdd.md](../../bdd/<feature>/<slug>-bdd.md) — observable behavior and scenarios
- [STATUS.md](../../STATUS.md) — current phase and active work

## Context

[Why does this feature exist? What user-visible behavior does it enable? What
downstream consumer needs it?]

## Behavior contract

[The contract this feature provides — public types, function signatures, CLI
flags, file outputs. Reference the ADRs that constrain it.]

## Anchor artifact

[The simplest concrete observable version of the thing. Built first, before
supporting code. e.g. "one CLI command that returns one result for one fixture
input."]

## Implementation order

[Concrete-first: anchor artifact, then supporting code. List ordered slices.]

## Proof requirements

1. [e.g. "Unit tests for X in <test path> green."]
2. [e.g. "BDD scenarios in bdd/<feature>/<slug>-bdd.md pass against the implementation."]
3. [e.g. "Real-artifact proof produces expected output; eyes-on review confirmed."]

## Non-goals

[What this spec explicitly does NOT cover. Defer to a future spec / ADR.]

## References

- [Other specs, ADRs, architecture sections.]
