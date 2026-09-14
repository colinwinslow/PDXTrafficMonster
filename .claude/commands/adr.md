---
description: Scaffold a new Architecture Decision Record at docs/decisions/NNNN-<slug>.md.
argument-hint: <slug>
---

Scaffold a new Architecture Decision Record at `docs/decisions/NNNN-$1.md`.

`$1` is the slug (e.g. `provider-interface-boundary`). If missing or invalid,
ask the user.

## Steps

1. **Validate slug.** Lowercase, hyphen-separated, no spaces.

2. **Find the next ADR number.**

   ```bash
   ls docs/decisions/ | grep -E '^[0-9]{4}-' | sort | tail -1
   ```

   Extract the number, increment by 1, zero-pad to 4 digits.

3. **Create `docs/decisions/NNNN-$1.md`** from this template (set the real
   number, derive the title from the slug, use today's date):

   ```markdown
   ---
   id: NNNN
   title: <Human-readable title — derive from slug; user can edit>
   status: draft
   date: YYYY-MM-DD
   supersedes: []
   superseded-by: null
   tags: []
   ---

   # ADR-NNNN: <Title>

   ## Context

   [What situation forced this decision? 3–5 sentences.]

   ## Decision

   [The decision in 1–2 sentences. Bold the load-bearing claim.]

   ## Rationale

   [Why this over the alternatives. Bullets OK.]

   ## Consequences

   **Enables:**
   - ...

   **Constrains:**
   - ...

   **Open:**
   - ...

   ## References

   - [Other ADRs, specs, architecture sections]
   ```

4. **Add an entry to `docs/decisions/README.md`** under the ADR list, in numeric
   position, with the `(draft)` label.

5. **Report the path.** Do not promote `status: draft` → `accepted` without
   explicit user confirmation. Promotion happens at `/closeout`, which also syncs
   the index label.

## Rules

- ADRs are immutable once `accepted`. Supersede by writing a NEW ADR that names
  the old one in `supersedes:` — never by editing the accepted one.
- One file per decision. Don't combine multiple decisions in one ADR.
- Cross-reference related ADRs in `## References`.
