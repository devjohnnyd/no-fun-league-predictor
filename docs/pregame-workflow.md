# Pregame workflow

Every output uses a new path. Original forecasts and published research artifacts are immutable. `scores` refreshes outcomes only; `prepare` rebuilds pregame features; `forecast` issues a new saved prediction. None is a scheduled job.

## Acquire and validate statistics

```powershell
python -m nfl_predictor acquire --start 2026 --end 2026 --output data/raw/new-week11
python -m nfl_predictor dataset --bundle data/raw/v4-2026-11-15 --bundle data/raw/v4-2026-11-15-ngs --bundle data/raw/new-week11 --start 2022 --end 2026 --output data/snapshots/new-week11.json.gz
```

On a clean clone, first acquire 2022–2026 into a fresh bundle; the example's older raw bundles are ignored local downloads. Later bundles override the same named source from earlier bundles, retaining exact receipts. The committed derived snapshot supports offline research without these downloads. All completed games before the target week must have results and play-by-play. Inspect quality exclusions, charting/tracking coverage and source timestamps.

Refresh venue metadata and logos with `metadata --dataset ... --output data/raw/new-metadata --assets assets/team-logos`. Review geocoding ambiguity and neutral venues; never fall back to the home NFL stadium for a neutral game. Preserve a versioned verified metadata JSON for fitting and preparation.

## Fit for the intended week

```powershell
python -m nfl_predictor research --dataset data/snapshots/new-week11.json.gz --venues data/snapshots/venues-v4-2026-11-15.json --season 2026 --week 11 --output reports/new-week11-research
```

Every game uses prior weeks only, including preprocessing and calibration. New families remain experimental shadows. Do not use the number of known Week 10 misses a candidate flips to choose a model. The issue command requires the model's cutoff, dataset and venue hashes to match preparation.

## Preliminary review and release

```powershell
python -m nfl_predictor prepare --dataset data/snapshots/new-week11.json.gz --venues data/snapshots/venues-v4-2026-11-15.json --season 2026 --week 11 --output data/raw/week11-pregame
python -m nfl_predictor check --manifest data/raw/week11-pregame/reviewed-manifest.json
python -m nfl_predictor forecast --dataset data/snapshots/new-week11.json.gz --venues data/snapshots/venues-v4-2026-11-15.json --research reports/new-week11-research/research.json --prepared data/raw/week11-pregame/prepared.json --output reports/week11-preliminary
```

Preparation refreshes eligible pending Sunday/Monday games, depth charts, injuries and kickoff weather; resolves projected QB/backup and kicker; verifies HC/OC/DC from official team pages; and builds the complete feature vector. Review projected starters, unmapped players, injury replacements and roof uncertainty. An ESPN depth chart is a projection, not a verified official inactive list. Unknown tracking/replacement measurements remain missing with training-only imputation and explicit missingness indicators.

Preliminary maximum source ages: statistics 48 hours, injury/depth 24 hours, weather 12 hours, staff seven days. Feature preparation must be no more than 30 minutes old. `forecast` rechecks live game status and kickoff, rebuilds the vector, and refuses target-week model leakage, changed inputs or a started game. These thresholds are operational safeguards, not learned effects.

Preserve small reviewed evidence packages using `python -m scripts.save_reviewed_inputs --prepared ... --output reports/new-inputs`. This retains summary/depth responses, exact features and source receipts without bulk data. Issue using its `prepared.json` so the retained prepared hash can be verified.

## Final review near kickoff

Run a fresh `prepare` with `--review review.json`, then `check --final` and `forecast --final`. Final releases must be within two hours of kickoff. Feature vectors must be at most ten minutes old; injury/depth/inactive evidence at most two hours old; weather at most six hours old.

The review file has `games.EVENT_ID.teams.TEAM` overrides for reviewed QB/backup, injuries and staff; and `games.EVENT_ID.sources` for verified weather, staff or inactives. Every receipt needs `event_id`, `url`, offset-aware `retrieved_at`, `status: "ok"` and supporting evidence. The official inactive receipt additionally needs `official: true` and `verified_teams: ["HOME", "AWAY"]`; reconcile those lists with feature-context injury/QB overrides. Retain separately linked evidence for both teams. Retractable roofs need a documented decision with `roof_decision_verified: true` and correct `enclosed_verified` conditions for final release. Do not invent verification fields to pass a check.

Weather must carry `valid_at` near kickoff, `temperature_f` and `wind_mph`, or verified enclosed conditions. Scenarios show alternative QB/availability/roof conditions; they are sensitivities, not probability confidence intervals. Actual arrival dates and travel itineraries are unknown.

## Benchmarks and results

ESPN-listed paired moneylines are retained only when observed before kickoff and within ten minutes before issue. Margin is removed within each book; latest observations are aggregated by median across books. They benchmark predictions and never enter features. Optional `forecast --market-quotes quotes.csv` accepts `event_id,book,home_price,away_price,observed_at,url` with paired American prices. Future/stale quotes are excluded. The optional Odds API library adapter reads `ODDS_API_KEY` from the environment and sends it in a header; it was not called or tested with a paid account.

After games, run `scores` and `score` into new paths. Compare saved primary/shadow Brier/log loss, accuracy, calibration and matched-game benchmarks. Historical schedule prices lack reliable timestamps and remain descriptive only. More than one prospective week is needed before promoting a new feature family.
