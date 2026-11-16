# Model research v4

New families are shadow candidates. Historical results use revised public data and timing assumptions; no prospective improvement is claimed.

| Family | Calibrated | Selection Brier | Correct / games |
|---|---|---:|---:|
| efficiency_qb | False | 0.220657 | 171 / 271 |
| special_teams | False | 0.222997 | 163 / 271 |
| body_clock | False | 0.223435 | 170 / 271 |
| replacement_injuries | False | 0.223634 | 162 / 271 |
| scheme_matchups | False | 0.223710 | 162 / 271 |
| v2_baseline | False | 0.224066 | 163 / 271 |
| special_teams | True | 0.224113 | 168 / 271 |
| scheme_matchups | True | 0.224741 | 164 / 271 |
| travel_weather | False | 0.224770 | 167 / 271 |
| body_clock | True | 0.225177 | 167 / 271 |
| replacement_injuries | True | 0.225320 | 161 / 271 |
| pressure_matchups | False | 0.225379 | 162 / 271 |
| qb_decisions | False | 0.225790 | 161 / 271 |
| tracking_skill | False | 0.225863 | 161 / 271 |
| v2_baseline | True | 0.226183 | 164 / 271 |
| travel_weather | True | 0.226370 | 168 / 271 |
| efficiency_qb | True | 0.226399 | 170 / 271 |
| combined | False | 0.226731 | 172 / 271 |
| opponent_adjustment | False | 0.227299 | 161 / 271 |
| tracking_skill | True | 0.227460 | 163 / 271 |
| pressure_matchups | True | 0.228128 | 164 / 271 |
| qb_decisions | True | 0.228228 | 168 / 271 |
| opponent_adjustment | True | 0.229969 | 166 / 271 |
| combined | True | 0.230181 | 169 / 271 |

Selected research configuration: **efficiency_qb**. Primary future forecasts retain the v2 feature family with freshly rebuilt inputs.

See `research.json` for chronological policy, paired comparisons, calibration, error slices, source coverage and limitations.

## Delivered release

The public-source dataset reconciles **149 completed 2026 regular-season games** through Sunday night. It preserves game/QB/team identifiers, exact source receipts and coverage exclusions. All **136 games through Week 9** are available for the target Week 10 feature cutoff; Week 10 results never enter its training or statistics. Historical data use revised source records, final injury reports, recorded starting QBs and observed weather, so retrospective performance is conditional on timing assumptions.

Fresh Monday preliminary forecasts were saved at **13:14:25 UTC** and **13:35:40 UTC November 16, 2026**, before the 01:15 UTC November 17 kickoff. Both choose **BAL at 66.7%**. The second also saves a separate experimental total-points projection: **40.8**, with an **80% empirical predictive range of 26–57**. These remain preliminary pending the final official inactive-list review. The frozen November 10 picks remain unchanged.

At the 13:18 UTC score refresh, the original batch is **9–3 in 12 completed games (75%)**, Brier **0.191743**, log loss **0.566741**, with Monday pending. This is a small initial live sample. `latest-score.json` contains each result and original probability.

## What the additional metrics show

The simpler efficiency/QB family wins 2025 selection. Combining every new metric raises correct picks to 172/271 but worsens Brier to 0.226731; that is not sufficient evidence of better probabilities. New families therefore stay as separately saved shadow predictions rather than replacing the primary forecast.

The body-clock family improves 2025 Brier from **0.224066 to 0.223435** and correct picks from 163 to 170. In the already-examined 2026 Weeks 1–9 sample, its Brier difference is **+0.002564** (worse), with an exploratory week-bootstrap 95% interval **−0.000822 to +0.005278**. This is mixed evidence, not a validated fixed travel penalty. The Monday visitor travels three hours east, but kickoff is **5:15 p.m. on the Chargers' home clock**, not a 10 a.m. early-game exposure. Arrival/acclimation times are unknown.

For Monday, saved home-win probabilities are 60.3% efficiency/QB, 62.5% body clock, 60.7% combined and 66.7% primary. These fitted-model differences are not isolated causal estimates of travel. Independent Elo is saved separately. The first release's aligned ESPN-listed DraftKings prices imply **66.4% BAL** after proportional margin removal. Prices and model observations are aligned within ten minutes; missing benchmarks remain missing.

## Three brochure games

The user chooses the three matchups each week. The attached Week 10 card prints MIN/GB **42.5**, SEA/LV **43.5**, PIT/CIN **47.5**. Final totals are **40 (Under)**, **34 (Under)** and **56 (Over)**. The lines arrived after completion and no pregame totals predictions exist for those games, so they are historical outcomes with **zero evaluated O/U model picks**. `brochure-results.json` and `data/cards/2026-week10.json` preserve that distinction.

The separate total-points regression selected the context family (ridge 150). In 2025 it has **10.587 MAE**, **13.357 RMSE** and **76.8%** coverage for the nominal 80% residual interval. In the previously examined 2026 Weeks 1–9 sample, MAE is **11.387** versus **11.606** for a prior-training-mean baseline. Tied NFL games are included (136 diagnostic games vs 135 decisive winner-model games). No timestamped historical brochure lines are available, so these errors do not establish O/U accuracy or a betting edge. Probabilities and ranges remain experimental.

## Dashboard and verification

The responsive dashboard displays all 14 games, 32 official NFL logos, current/final scores, the preserved original record, saved forecast revisions, QB/body-clock details and three printed-total cards. Filters/search/sort and source inspection retain their exact populations. A same-origin feed updates scores every minute while visible; the backend cache is 30 seconds. A provider interruption preserves the previous rows/time and shows an unavailable warning. A static package and hosting guide are supplied; no external deployment or recurring job was created.

Validation includes the complete Python suite, Node dashboard helper tests, clean locked dependency install, verified protected runtime/source build, exact original-v2 reproduction, and desktop/tablet/mobile browser checks. Browser screenshot capture works, but saving those images through the computer-use runtime was denied by its filesystem boundary; no screenshot attachments are claimed. Local preview is the visual deliverable. See the repository verification record for final counts and Git commit.

FTN charting adaptations are CC BY-SA 4.0 with FTN/nflverse attribution; NFL team marks retain their owners' rights. See `DATA_LICENSES.md` at repository root.
