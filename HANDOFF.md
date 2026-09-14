# HANDOFF — PDXTrafficMonster

## Repository

```text
Local path:  /home/claude/repos/PDXTrafficMonster
GitHub:      (not yet created)
```

## What this project is

PDXTrafficMonster is an animated data visualization of how Portland traffic
redirects during the five-week closure of I-5 southbound at the Rose Quarter
(closed starting 2026-09-11, reopening expected mid-October 2026). It's built
on real public traffic data — not a simulation — and the goal is to show
drivers visually rerouting onto I-405, I-205, and the surface street grid as
the closure squeezes the primary corridor.

## Current direction

Phase 0: research is done, concept and stack are not yet chosen. The research
session identified PORTAL (Portland State University's regional transportation
data archive) as the strongest candidate primary source — free, public,
no partnership gate — because it's the only source with freeway-level
speed/volume data across all three affected corridors (I-5, I-405, I-205)
simultaneously. ODOT TripCheck (incidents, message signs) and WSDOT (Vancouver,
WA side) round it out as supporting/annotation data. Waze and Google's real
traffic data were ruled out: Waze CCP is partnership-gated and forbids
redistribution, and Google's comparable historical data is an enterprise
BigQuery product with no public access path.

## Latest completed work

Repo seeded 2026-09-14: workflow kit installed, `docs/research/
i5-closure-data-sources.md` written up from the research session. No
visualization code exists yet.

## Recommended next step

Pull a real sample from PORTAL (station list + field names near the Rose
Quarter) to confirm the data is usable before committing to a stack — then
write the ADR that picks the visualization concept and rendering approach.
See `STATUS.md` "Active work" for the full breakdown.

## Constraints / guardrails

- Don't use Waze data or scrape Google Maps traffic tiles — see
  `CLAUDE.md` invariant 2 and the research note's "dead ends" section.
- The closure is a real, time-boxed event (started 2026-09-11, ~5 weeks) —
  don't let the project drift past the point where the data is still
  timely/interesting.
