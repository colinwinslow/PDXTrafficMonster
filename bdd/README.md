# BDD Tree

Behavior scenarios live here, grouped by feature: `bdd/<feature>/<slug>-bdd.md`,
paired with the spec at `docs/specs/<slug>.md`. Scaffold both with `/spec`.

## Convention

This kit uses **markdown Given/When/Then** scenarios plus a separate **evidence
file**, kept distinct from the spec:

```
bdd/<feature>/
  <slug>-bdd.md        # the scenarios (Given/When/Then)
  <slug>-evidence.md   # raw proof each scenario was hit (produced by the slice)
```

This separation is deliberate: the BDD is the *contract* (stable), the evidence
is the *proof* (regenerated per run). The `bdd-evidence-reviewer` subagent checks the evidence honestly hits every
scenario.

## Evidence files contain raw output

An evidence file shows **actual outputs** — test runner output, exact CLI
invocations with observed results, file contents read back — not "✓ passed."
Summary-only evidence is a review CONCERN.

## If your stack uses Gherkin

Gherkin `.feature` files (pytest-bdd, behave, Cucumber) are an equally valid
BDD shape. If you use them, keep the same discipline: scenarios are the
contract, and an inspectable evidence trail proves each was hit. The review
pass adapts — it cares about honest evidence, not the file format.

## Layout

```
bdd/
  <feature-a>/
    <slug>-bdd.md
    <slug>-evidence.md
  <feature-b>/
    ...
```
