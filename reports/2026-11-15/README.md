# November 15 model and forecast update

The original live batch is **8–3 (72.7%)** across 11 completed games, with two games unfinished at the result snapshot. Brier score is **0.18741**. Results were fetched November 16 at 01:55 UTC / November 15 at 8:55 p.m. Eastern from the [ESPN Week 10 scoreboard](https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week=10&limit=1000). This is a partial first-week sample, not evidence of a sustained 73% win rate.

The model assigned about **3.52 expected losses** across those same completed games; it lost three. That comparison alone does not establish calibration. Confidence bands and individual results are in [live-week10.json](live-week10.json). Green Bay (72.2%), Houston (67.5%) and New Orleans (52.5%) were the misses. See the [review](../../docs/week10-review.md).

## New metrics and results

Added lagged QB-hit/protection interactions, OL absence × opponent-rush proxy, prior-game top-five OL continuity, QB changes and prior QB dropbacks with the same head coach. Missing inputs retain explicit missingness indicators; preprocessing uses training rows only. No statistics from the target game enter these additions.

| Family | 2025 selection correct / games | 2025 Brier | 2026 Weeks 1–9 correct / games | 2026 Brier |
|---|---:|---:|---:|---:|
| Efficiency + QB | 171 / 271 | 0.220657 | 87 / 135 | 0.222413 |
| v2 full model | 162 / 271 | 0.224304 | 90 / 135 | 0.216988 |
| v2 + protection | 164 / 271 | 0.224247 | 89 / 135 | 0.216399 |
| v2 + QB transition | 163 / 271 | 0.225177 | 89 / 135 | 0.219566 |
| v2 + OL continuity | 165 / 271 | 0.225171 | 88 / 135 | 0.217312 |
| Combined | 170 / 271 | 0.223932 | 84 / 135 | 0.222354 |

Lower Brier scores are better. Each family uses its penalty selected on rolling 2024 results. Feature-family selection uses rolling 2025 Brier score; the winner is efficiency + QB. Every fit uses only earlier weeks. The combined model selected penalty 150; the others selected 60.

**Decision:** retain v2 as the existing live baseline and keep the new fitted artifact and additions as research candidates. Pass protection offers a small diagnostic probability improvement, but these results do not justify declaring a reliable accuracy gain or replacing the model after three misses. The original 2026 v2 probabilities reproduce with a maximum absolute error of `2.78e-16`.

The 2026 diagnostic period had already been inspected. The candidate ideas were designed after the Week 10 losses; this evaluation is not an untouched prospective test. Final historical injuries, actual recorded starters, observed weather and revised public data also limit what can be inferred about real pregame performance. A future timestamped shadow trial is needed before promoting a candidate.

## Operational changes

The new collector fetches into a new run directory with exact timestamps and hashes. The preflight rejects started games, missing/stale inputs, wrong-game evidence and statistics from the wrong week. Final checks require reviewed official inactive lists for both teams. It does not silently assume calm weather or healthy players.

The [latest Monday preflight](pregame-checks-latest.json), checked at 9:03 p.m. Eastern, correctly returns not ready: statistics and coaching verification are still missing. The [newer source snapshot](../../data/snapshots/pregame-week10-2026-11-16.json) includes fresh depth/injury evidence and an explicitly labeled Baltimore city-level weather proxy at kickoff. This resolves the missing-weather flag in the [earlier check](pregame-checks.json). Final official inactive verification is still required near kickoff. No new picks were issued using incomplete inputs. The collector refreshes evidence and outcomes; it does not yet rebuild a live feature vector automatically.

## Evidence and verification

- [Evaluation and fitted research model](evaluation.json): all tuning/selection/diagnostic scores, hashes, feature coverage and limitations.
- [Retrospective per-game predictions](retrospective-2026.csv) and [candidate feature matrix](features.csv).
- [Result source snapshot](../../data/snapshots/week10-results-2026-11-16T0155Z.json) and [frozen forecasts](../../archive/session-2026-11-10/enhanced/model.json).
- `python -m unittest discover -s tests -v`: 31 tests passed at implementation, including v2 reproduction, strict prior-week training, future-stat exclusion, lineup missingness, source freshness, inactive coverage, geocoding disambiguation, depth-chart coverage, ties and immutable scoring. GitHub Actions is configured separately; local success does not establish hosted CI success.
