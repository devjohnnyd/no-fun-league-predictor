# Data and reproducibility

The repository retains public-source derived inputs, original forecast snapshots, the delivered workbook, evaluation code and results. Bulk downloads, local Python/Node dependencies and caches are ignored. Data rights remain with their respective owners; this project does not claim ownership of NFL/provider data.

| Input | Source | Use / limitation |
|---|---|---|
| Schedules, scores, coaches and recorded starting QBs | [nflverse schedule data](https://github.com/nflverse/nfldata/blob/master/data/games.csv) | Recorded historical starters are assumed known before kickoff in retrospective tests. |
| EPA, CPOE, sacks, QB hits, explosives | [nflverse play-by-play](https://github.com/nflverse/nflverse-data/releases/tag/pbp) | nflfastR-derived measures can be revised later; hits are an incomplete pressure proxy. |
| Weekly injuries | [nflverse injuries](https://github.com/nflverse/nflverse-data/releases/tag/injuries) | Final weekly records lack reliable publication times. Conflicting duplicate keys were excluded in v2. |
| Player participation and OL continuity | [nflverse snap counts](https://github.com/nflverse/nflverse-data/releases/tag/snap_counts) | Prior-game snap shares proxy importance. Top-five OL overlap proxies continuity, not projected starting lineup certainty. |
| Player identifier crosswalk | [nflverse players](https://github.com/nflverse/nflverse-data/releases/tag/players) | ESPN/PFR/GSIS joins can miss players. |
| Live schedule, scores, depth and injury context | [ESPN scoreboard API](https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard) | Public endpoints can change. Current injury/depth responses do not independently confirm official inactive lists. |
| Weather | [Open-Meteo documentation](https://open-meteo.com/en/docs) | Forecasts nearest kickoff at venue coordinates or a disclosed unique city/country/state proxy. Historical observed weather does not prove pregame forecast accuracy. |
| HC / OC / DC | Official team coaches pages | URLs and names are retained in the original `context.json`; changes require fresh verification. |
| Play-action, motion, screens, blitz, catchability, interception-worthy throws and QB-fault sacks | [FTN charting via nflverse](https://nflreadr.nflverse.com/reference/load_ftn_charting.html) | One-to-one game/play joins; coverage reported. Import time does not establish first publication. FTN attribution and CC BY-SA 4.0 apply to charting adaptations. |
| Actual pressure and pressure-to-sack conversion | [PFR advanced passing via nflverse](https://nflreadr.nflverse.com/reference/load_pfr_advstats.html) | PFR and nflverse denominator universes differ. Excludes impossible rates; uses eligible dropbacks to exposure-weight reported fractions. |
| Time to throw, receiving separation/YAC, rushing yards over expectation | [NFL Next Gen Stats via nflverse](https://nflreadr.nflverse.com/reference/load_nextgen_stats.html) | Weekly qualifying players only; week-zero season summaries excluded. Actual release assets use `.csv.gz`. Missing backup/low-volume quality stays unknown. |
| Logos and venue/body-clock metadata | [Official NFL team logos](https://www.nfl.com/teams/), ESPN teams, Open-Meteo/GeoNames | All 32 logo URLs/hashes retained. City-level travel, date-specific IANA zones, game-specific neutral venues; not actual arrival/acclimation data. |
| Three weekly over/under lines | User-provided brochure photo or exact supplied totals | Preserve printed lines independently of market prices. Week 10 photo arrived after the three Sunday games; no pregame O/U picks are backfilled. |

Version 4 connects these sources to one shared historical/live feature engine. `prepare` rebuilds current feature vectors, `forecast` validates and saves primary/shadow predictions, `scores` fetches fresh outcomes, and `serve` supplies the dashboard feed. The compact v4 snapshot reconciles all 149 completed 2026 games through Sunday night, November 15. The target Week 10 model still trains only through Week 9. Four conflicting injury rows, one impossible 150% pressure observation and 2,378 week-zero NGS rows were excluded; see the snapshot's `quality` for exact coverage and counts. Unmapped snaps remain reported.

The separate total-points model uses the same temporal feature engine and earlier-week cutoffs, includes tied NFL games, and reports MAE/RMSE and empirical predictive intervals. Its over/under probabilities are experimental: timestamped historical brochure lines are unavailable, so no historical betting edge is claimed. [Metric definitions](metrics.md), [weekly cards](weekly-cards.md) and [licensing](../DATA_LICENSES.md) describe the operational limits.

`data/snapshots/history-2026-11-10.json` derives a compact schedule, QB-to-team mapping (including backups), and prior-game top-five OL snap leaders from the original raw cache. Its hashes identify the original cached source files. Importing the cache now does not change its November 10 data cutoff. The original collection script recorded execution time even when reusing an existing file; do not interpret those legacy timestamps as proof of a new download. The new collector always fetches into a new run directory and hashes the exact response bytes.

Recreate the compact snapshot, if you have the original downloads:

```powershell
python scripts/prepare_history.py --raw PATH_TO_ORIGINAL_RAW_CACHE --output data/snapshots/new-copy.json
```

Run evaluation from a clean clone with no original raw cache:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m nfl_predictor evaluate --output reports/reproduction
```

The evaluator uses 2022 for available warmup history; 2023 begins model training. Each evaluation game uses only earlier seasons/weeks for statistics, preprocessing and fitting. Penalties are chosen using rolling 2024 Brier score; feature families are selected on rolling 2025 Brier score. The already-inspected 2026 Weeks 1–9 results are diagnostic. The three Week 10 losses informed candidate design, so no test here is a new prospective validation. Probability estimates condition on a decisive result; ties are excluded from the binary fit and counted separately.

`evaluation.json` stores the fitted research model, policy, metrics, caveats, input hashes and v2 reproduction error. Existing v2 probabilities must reproduce within `1e-7`. The entire pregame matrix is retained for inspection, but feature selection explicitly lists allowed fields; scores and betting lines never enter the feature lists. All raw/derived rates use prior-game numerators and denominators rather than unweighted averages of player/game averages.
