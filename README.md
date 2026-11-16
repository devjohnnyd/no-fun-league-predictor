# No Fun League Predictor

An auditable NFL tracker and probability model owned by [devjohnnyd](https://github.com/devjohnnyd). Track every regular-season game and its market over/under, including Thursday, in a responsive weekly dashboard.

## Current release — November 16, 2026

- **149 completed games** reconciled against play-by-play across the 2026 season through Sunday night.
- Original Week 10 picks: **9–3 (75%)**, Brier **0.191743**, with Monday pending. Twelve completed picks are a small sample.
- Fresh Monday preliminary forecast: **BAL 66.7%** vs LAC, issued **13:14 UTC November 16**. The original Tuesday forecast stays unchanged. Official final inactive lists were not yet available.
- Shared historical/live feature builder, independent Elo and timestamp-aligned market comparisons, scenarios, chronological feature-family tests and immutable experimental forecasts.
- All 14 Week 10 matchups, 32 official NFL team logos, live/final scores, search, slate/status filters, saved picks and home-clock kickoff details. Score refresh never regenerates picks.
- [Three weekly brochure totals](docs/weekly-cards.md), chosen by the user, with a separate experimental total-points model and historical/result tracking. Week 10 printed lines are 42.5, 43.5 and 47.5; those games were already final when supplied, so no O/U picks are backfilled.

Travel now includes direction, zones crossed, kickoff on the team's home clock, early/late exposure and scheduled-rest interaction. IANA zones handle daylight saving and international date changes. These are experimental inputs: historical comparisons are mixed and actual arrival/acclimation times are unknown.

The original v2 feature family remains the primary probability model, rebuilt with fresh inputs. New families are saved as shadows for future evaluation. More metrics have **not** established better live accuracy. See [research and release evidence](reports/2026-11-16-complete/README.md), [metrics](docs/metrics.md), [data/limitations](docs/data-sources.md), and [Week 10 miss review](docs/week10-review.md).

## Dashboard

Requires Python 3.11+, Node 22.12+ (Node 24 recommended), and npm:

```powershell
python -m pip install -e .
npm ci --prefix web
npm --prefix web run build
python scripts/configure_dashboard.py --snapshot data/snapshots/dashboard-week10-release-2026-11-16.json --complete --copy-assets
python -m nfl_predictor serve --season 2026 --week 10 --metadata data/snapshots/venues-v4-2026-11-15.json --dataset data/snapshots/dataset-v4-2026-11-16.json.gz --forecast archive/session-2026-11-10/enhanced/model.json --forecast reports/2026-11-16-complete/monday-with-totals/forecast.json
```

Open **http://127.0.0.1:4173/**. Choose a week to inspect its complete slate. **Refresh data & analysis** updates scores and lines and starts a serialized pregame rebuild; add `--history-bundle data/raw/v4-2026-11-15` to the serve command to enable current-season statistical rebuilding with the existing historical bundle. See [line movement, original-pick preservation and printed cards](docs/weekly-cards.md). The local line ledger lives in `work/tracker/lines.sqlite3`; back it up to retain prospective history. Failed updates preserve the last successful data and timestamp. Static hosting requires a separately hosted feed/analysis service; it cannot run Python or update the SQLite ledger by itself. See [hosting and portable packaging](docs/hosting.md).

## Latest scores

Use a new output filename every time:

```powershell
python -m nfl_predictor scores --season 2026 --week 10 --output data/raw/latest-results.json
python -m nfl_predictor score --forecast archive/session-2026-11-10/enhanced/model.json --results data/raw/latest-results.json --output reports/latest-original-score.json
```

Completed, pending, tied and unavailable games stay separate. The original batch is never rewritten. New shadow batches can be graded with the same `score` command, which includes paired comparisons on identical games.

## Research and new picks

```powershell
python -m unittest discover -s tests -v
node --test tests/dashboard.test.mjs
python -m nfl_predictor evaluate --output work/baseline-reproduction
python -m nfl_predictor research --dataset data/snapshots/dataset-v4-2026-11-16.json.gz --venues data/snapshots/venues-v4-2026-11-15.json --season 2026 --week 10 --output work/research-reproduction
```

Offline evaluation uses committed derived inputs. Penalties are tuned on 2024, configurations selected on 2025 Brier score, and 2026 Weeks 1–9 labeled previously examined diagnostics. Preprocessing/fitting use only earlier weeks. Historical final injuries, recorded starters, observed weather and revised statistics are conditional timing assumptions, not proof of prospective performance.

[Pregame workflow](docs/pregame-workflow.md) documents fresh acquisition → validation → model fitting → source review → feature rebuild → release. Required checks block stale/incomplete inputs or started games; final releases require verified official inactive lists for both teams. No background forecasting job is installed.

Original forecasts/workbook remain under `archive/session-2026-11-10/` and `reports/2026-11-10/`. Bulk downloads, dependencies, caches and built output are excluded from Git. [Data attribution and licensing](DATA_LICENSES.md) applies to provider-derived data and logos; the project does not claim ownership of those assets.
