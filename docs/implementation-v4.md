# Version 4 implementation record

Authorized scope: connect fresh data to forecast features; opponent-adjusted efficiency; replacement-aware injury/lineup changes; QB decision quality; pressure/blitz and scheme matchups; receiving/rushing tracking metrics; special teams and field position; travel and weather interactions; independent benchmarks; calibration, error slices, ablations and timestamped shadow forecasts.

Implementation sequence:

1. Acquire public data with immutable receipts and explicit missing-source coverage. Preserve all archived forecasts.
2. Aggregate only completed game data into versioned, reusable inputs; validate joins, units, source conflicts and completeness.
3. Use a common temporal feature builder for historical evaluation and live pregame forecasts. Rebuild inputs from current depth/injury/weather/coaching evidence rather than a frozen CSV.
4. Test the requested feature families separately, with training-only preprocessing, chronological selection, diagnostics and uncertainty. Keep the live baseline unless promotion is supported.
5. Issue pregame/shadow batches with exact issue times, model/source hashes, scenarios and release checks. Track independent Elo and timestamp-aligned, margin-removed market benchmarks.
6. Deliver readable reports, CLI documentation, regression/integration tests and verified commits under `devjohnnyd`.

Constraints: no purchased data or subscriptions are implied. Use public FTN charting via nflverse with required attribution and share-alike terms for derived charting data. Optional Odds API support reads a local environment key and never stores it; public ESPN prices or timestamped CSV imports provide alternatives. Missing feeds remain missing. Historical final injury reports, recorded starting QBs and observed weather retain their retrospective limitations. No candidate designed after the first live week is an untouched historical experiment.

Completion evidence: `reports/2026-11-16-complete/` contains the 2024 tuning/2025 selection/2026 diagnostic comparisons, 149-game validated current-season snapshot references, exact Monday pregame/shadow forecasts, paired Elo/market benchmarks, original 9–3 pick scoring and the three brochure outcomes. The common live feature builder and release checks are implemented. All new metric families remain experimental shadows; precipitation fitting, actual travel arrival/acclimation and complete historical coordinator responsibility remain external data limitations, not invented measurements.

User addition: support three user-selected brochure over/under games per week. `totals.py` adds separate chronological point-total regression, empirical predictive ranges, exact printed-line comparisons and push-aware tracking. The photo's Week 10 lines were supplied after the games and are scored only as historical outcomes. `docs/weekly-cards.md` documents the configuration and timing policy. The responsive dashboard includes these three cards, official logos, all matchups and a same-origin live feed; a portable static package and hosting guide are supplied without external publication.

User additions: build a quick responsive matchup dashboard for this week's full slate, using official NFL team logos and supporting a separately hosted live score feed. Add an independent body-clock/time-zone family: direction, zones crossed, kickoff in the team's home time zone, early/late kickoff exposure and interaction with scheduled rest. Use IANA zones on the actual date, wrap international phase differences at 24 hours, and distinguish scheduled rest from unknown arrival/acclimation time. Motivation includes [Smith et al. 2013](https://pubmed.ncbi.nlm.nih.gov/24293776/) and [Roy et al. 2017](https://pubmed.ncbi.nlm.nih.gov/28568314/); these observational studies do not establish a current causal win-probability adjustment.
