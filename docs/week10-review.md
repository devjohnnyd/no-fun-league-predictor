# Week 10 misses: facts, hypotheses and follow-through

This review refers to the original November 10 v2 forecasts. The first 11 completed games produced eight wins and three losses. Outcomes are saved in [the live scoring report](../reports/2026-11-15/live-week10.json). Postgame information explains what happened; it must not be inserted into pregame features.

| Miss | Original pick probability | What happened | Model implication |
|---|---:|---|---|
| Minnesota 30, Green Bay 10 | GB 72.2% | Minnesota recorded eight sacks. Cousins completed an important fourth-quarter drive. | Highest-priority confidence miss. Test pass-rush/protection and QB-transition context; inspect fresh OL availability. |
| Cleveland 27, Houston 24 | HOU 67.5% | Houston led 17–0, then had four straight second-half three-and-outs. Cleveland scored the winning TD with under a minute left. | A meaningful underdog probability remained. Do not add an unvalidated comeback or “clutch” bonus from this game. |
| Carolina 20, New Orleans 17 | NO 52.5% | A late 30-yard interference penalty helped set up Carolina's winning 54-yard field goal. | A near-even game. Avoid treating the narrow pregame preference as a strong prediction. |

Game facts are supported by the [Vikings recap](https://www.vikings.com/news/kirk-cousins-defense-win-packers-week-10-2026-observations), [Browns recap](https://www.clevelandbrowns.com/news/browns-27-texans-24-final-score-stats-game-recap) and [Saints recap](https://www.neworleanssaints.com/news/carolina-panthers-new-orleans-saints-2026-nfl-week-10-game-recap). The Saints also lost Pete Werner and Asim Richards during the game; those injuries cannot be treated as known pregame absences. The archived model already projected Cousins, so this was not simply a missed starting-QB substitution.

The plausible Green Bay mechanisms are hypotheses about a single game, not measured causal contributions. The archived Tuesday inputs were five days old by Sunday. That is a process gap worth fixing regardless of whether a fresh report would have flipped the pick. A specific late injury report being different from Tuesday still requires an actual snapshot comparison; no such change is assumed here.

## Changes implemented

- Reproducible lagged pass-protection, QB transition/coaching history and offensive-line continuity candidates, evaluated across earlier seasons.
- A separate 2024 penalty-tuning period and 2025 feature-selection period; already-examined 2026 results remain diagnostic.
- A freshness preflight and final inactive verification requirements, including rejection of forecasts after kickoff.
- Scoring by original probabilities, with Brier/log loss, expected losses, confidence bands, and separate unfinished/tied games.
- Versioned code, findings, forecasts, workbook and source receipts in the personal GitHub repository.

The new candidates show mixed results and remain experimental. The live baseline is preserved. The [evaluation report](../reports/2026-11-15/README.md) records the comparison without tuning model weights to turn these three losses into wins.
