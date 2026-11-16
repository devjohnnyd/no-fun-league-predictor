# No Fun League Predictor

An NFL game tracker and probabilistic winner model owned by [devjohnnyd](https://github.com/devjohnnyd). It tracks every regular-season game and forecasts all Sunday games plus Monday Night Football.

The November 10, 2026 forecasts and original analysis are retained as an audit baseline. Improvements are evaluated chronologically before they are used for new games. Forecasts are estimates conditional on a decisive result. Ties are tracked separately.

## Current state

- First live batch: **8–3 (72.7%)** in 11 completed games as of November 15, 2026, 8:55 p.m. Eastern. Sunday night was in progress; Monday night was pending. This is an early sample.
- Original probabilities, data, analysis scripts and the delivered workbook are committed under `archive/session-2026-11-10/` and `reports/2026-11-10/`.
- v3 adds reproducible research for pass protection, OL continuity and QB transitions/coaching history; a pregame freshness check; timestamped source receipts; and scoring with calibration bands. The additions are **experimental**, and v2 remains the live baseline.
- [Latest findings](reports/2026-11-15/README.md), [miss review](docs/week10-review.md), [pregame workflow](docs/pregame-workflow.md), [sources and limitations](docs/data-sources.md).

The collector does not yet rebuild a new live feature vector or automatically issue picks. Fresh team/QB statistics, coaching evidence, verified venue weather and official inactive checks still require review before new predictions. There is no background refresh job.

## Run locally

Python 3.11 or later:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
python -m nfl_predictor evaluate --output reports/my-reproduction
```

The evaluator runs offline using committed derived inputs. It tunes penalties on 2024, selects the feature family on 2025 Brier score, and reports the already-examined 2026 results as diagnostic. It also checks exact reproduction of the original v2 probabilities. A new output directory preserves existing results.

```powershell
python -m nfl_predictor refresh --season 2026 --week 11 --output data/raw/new-week11-run
python -m nfl_predictor check --manifest data/raw/new-week11-run/manifest.json
python -m nfl_predictor score --forecast archive/session-2026-11-10/enhanced/model.json --results data/snapshots/week10-results-2026-11-16T0155Z.json --output reports/new-week10-score.json
```

`check` exits with status 1 for missing/stale evidence. See the workflow for completing reviewed manifests and final inactive checks. The scorer never overwrites the original forecast or an existing output file. GitHub Actions runs the offline tests on pushes and pull requests.

## Baseline and interpretation

- 2026 retrospective Model 2 results through Week 9: 90 correct picks in 135 decisive games (66.7%).
- Historical injury reports lack complete publication timestamps. Historical weather inputs are observed conditions. Those checks are exploratory and do not establish prospective accuracy.
- The first live forecast batch was issued November 10 for November 15–16. New model versions must not rewrite those forecasts.

Added metrics have not demonstrated a reliable live accuracy improvement. The simpler efficiency/QB family wins the 2025 selection period; v2 performs better on the already-examined 2026 Weeks 1–9 sample. Pass protection slightly improves 2026 Brier score but loses one correct pick. More inputs do not automatically yield better forecasts.

Public bulk downloads and local runtime dependencies are excluded from Git. Source URLs, hashes, derived analysis and forecast snapshots are versioned. Archived scripts retain their original session assumptions; use the `nfl_predictor` package for the portable evaluation, refresh and scoring commands.
