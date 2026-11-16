# Metric catalog and analysis policy

Features are home-minus-away differences unless specified. `engine.py` defines formulas; `research.json.models.*.model.names` lists fitted inputs. Outcomes, moneylines and target-game statistics are never predictors.

| Family | Measurements | Interpretation / limits |
|---|---|---|
| Efficiency/QB baseline | Offense/defense EPA, recent net EPA, QB EPA/CPOE/effective dropbacks and low-sample flag, sack rates, explosives, home field, rest | Current team history plus prior-season last 12 games at weight .45; QB prior two seasons decay .65/year. Rates use summed numerators/exposure and shrinkage. |
| Baseline context | Snap-weighted OL/skill/defensive absences, questionable workload, new HC, wind/cold × pass tendency | Fresh pregame context replaces historical projections live. Final retrospective injuries and observed weather have timing limitations. |
| Opponent adjustment | Ridge-estimated offense/defense all/pass/rush EPA strength, opposing-unit matchups, early-down success | Prior weeks only, exposure weighting and 300-play ridge regularization. Shrunk estimates, not certain rankings. |
| Replacement injuries | Backup workload, measured skill-quality loss, simultaneous OL/secondary absences | Recent four team games include absences. Historical snap-leader replacement proxies; live depth-slot identities override. Unknown quality stays missing; no invented OL/defender grades. |
| QB decisions | Interception-worthy, catchable, dropped and QB-fault-sack charting rates; NGS time to throw | FTN judgment/coverage and NGS qualifying thresholds apply. Separate from realized interceptions and outcome luck. |
| Pressure/blitz | PFR pressure allowed, opposing pressure generation, pressure-to-sack conversion, QB EPA vs blitz × defense blitz tendency | Impossible rates excluded. PFR/nflverse universes differ; reported pressure fractions are weighted using eligible nflverse dropbacks. |
| Scheme matchups | Play-action/motion/screen tendency × opposing conditional EPA; deep-pass matchup | Prior charted plays proxy scheme performance. HC/OC/DC verified live; historical coordinator/play-caller identities are incomplete, so no invented coordinator grades. |
| Tracking skill | Receiving separation, YAC over expectation, rushing yards over expectation/attempt | Weekly NGS only; week-zero summaries excluded. Lagged role proxies weight players; low-volume/backup coverage gaps explicit. |
| Special teams | Special EPA/play, starting field position, projected-kicker residual vs prior distance/wind/cold cells | Kicker projected from live depth or lagged historical identity. Cell/player shrinkage; nflfastR `fg_prob` is not kick make probability and is not used here. |
| Body clock | Signed phase shift, zones crossed, east/west magnitude, hours before noon/after 8 p.m. on home clock, shift/scheduled rest | IANA dates handle DST/Phoenix; international differences wrap to ±12 hours. Noon/8 p.m. are modeling proxies, not biological thresholds. Actual arrival/itinerary/acclimation unknown. |
| Travel/weather | City-to-venue great-circle km, consecutive road games, wind × air depth/kicker quality, precipitation × pass tendency | Neutral games need game-specific coordinates. Rain interaction computed but excluded from fitting until varying history exists. Retractable roof decisions require verification. |

Missingness remains explicit. Numerical preprocessing uses training medians, missing indicators and training-only standardization; that fallback is not a measured healthy player/calm weather/average backup. Required current QB/weather/staff and previous-week coverage failures block release.

## Validation

2022 supplies warmup, 2023 starts fitting. Rolling 2024 predictions tune ridge penalties (15/60/150) and calibration intercept/slope. Rolling 2025 Brier selects family/calibration; 2026 Weeks 1–9 are previously examined diagnostics. New families are tested individually with the baseline and together, alongside simpler efficiency/QB. Design followed known Week 10 misses; no historical period is claimed as a newly untouched test.

Reports retain accuracy/Brier/log loss, weekly metrics, calibration with Wilson accuracy intervals, confidence/neutral/rest/QB/injury/weather/time-zone slices, largest errors and paired Brier differences. Week-block bootstrap intervals (2,000 replicates) are exploratory and not adjusted for trying many models. Scenario ranges are sensitivities, not calibrated confidence intervals.

Independent Elo uses K=20, 55 home Elo points (zero neutral), .67 offseason carry, prior weeks only. Markets remove margin within paired book prices observed within ten minutes before exact issue. Untimed historical schedule moneylines cannot establish a fair forecast-time comparison.

Live/shadow grading uses saved probabilities and pre-kickoff issue time. Comparisons match primary and candidate predictions on identical decisive games. Ties, pending and missing records stay separate. Promote families on sustained chronological/prospective evidence, not one favorable week or a flipped known loss.
