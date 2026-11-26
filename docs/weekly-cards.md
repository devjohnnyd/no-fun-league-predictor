# Weekly over/under tracking

## Point spreads and the weekly toss-up

Every matchup shows its point spread when the provider has a quote. The spread model projects home score minus away score from historical team, quarterback and game features. Its training excludes the target week. Rolling 2024 errors calibrate the projected margin distribution and 2025 margin error is reported beside a historical mean baseline. These comparisons measure score-margin error. Cover probabilities are experimental.

The first directional spread pick keeps its original line even if the quote or projection changes. A push occurs when the selected team's final score plus its spread equals the opponent's score. The weekly record counts wins, losses, pushes and pending picks. Game details show when each line and pick were observed.

The toss-up highlights the saved winner projection closest to 50/50 and shows both teams' win probabilities. Before any winner picks are ready, it highlights the tightest available pregame spread as an early watch.

Every NFL game has its own market-total selection, including Thursday and other non-Sunday games. The optional three-game printed card remains a separate fixed-line contest view. No brochure is required for the full slate.

The week selector loads any regular-season week from the reviewed season schedule. Each game shows its available provider total, first observed total, same-provider movement, scoring projection, latest line analysis, original tracked market pick and eventual result. Details include timestamped quote history and the projection's issue time. Missing quotes and forecasts stay unavailable; completed games never receive retrospective picks.

**First observed** means the first quote this tracker captured, not the market opening line. Movement compares the same provider; the first model pick retains its own line even if the provider changes. Pregame observations and analyses are appended to `work/tracker/lines.sqlite3`. Preserve/back up this local file to retain tracking history. The original pick is settled against its saved line; pushes and pending games stay separate. Provider update time is unknown. New line or model revisions never rewrite an earlier selection.

**Refresh data & analysis** fetches scores/lines immediately, then starts one background job: download current-season public statistics, rebuild with the historical source bundle, refresh QBs/injuries/staff/weather, fit chronological winner and total models, and save new pregame revisions. Progress and blocking reasons appear in the UI. One-minute score/line polling does not automatically retrain. Full refresh requires `serve --history-bundle data/raw/v4-2026-11-15` (or your actual historical source bundle; repeat the flag for additional bundles). Raw downloads, quote history and immutable refresh runs remain local and ignored by Git. Incomplete preceding-week statistics, missing required evidence, stale inputs and passed kickoffs block new picks while preserving existing selections and updated quotes.

## Starting QBs and locked bets

Every game card names the starting QBs the saved pick was built on. When a later input check projects a different starter (a release, benching or injury), the card flags the change even if the model could not release a new forecast, for example because the new QB has no statistics identity yet.

**Lock in bet** records the bet at that moment. The server freezes its own current view of the game: winner pick and probability, forecast issue time, both starting QBs and their status, designated injuries, kickoff weather, and the latest spread and total with any model lean. Locks are allowed only before kickoff, once per game, and are never rewritten. They live in `locks.sqlite3` beside `lines.sqlite3` in the tracker state directory; back it up with the line ledger.

Afterward the card shows how many things changed since the lock, and Details compares **At lock** with **Now** (or the last pregame view once the game starts). Major changes are ones that could flip a bet: a different starting QB, a flipped pick or lean, or a player newly ruled out. Line moves, probability shifts of 3+ points, wind or temperature swings and other status changes are listed as minor. Final games grade the bet exactly as locked (winner, spread and total at the locked lines) and note whether the latest pregame pick would have done better.

Locking requires a password from the `NFL_LOCK_PASSWORD` environment variable on the server (locally before `serve`, or an Azure app setting for the hosted site). Without it, locking is off. The password is never stored in Git; the browser remembers it locally after the first successful lock.

## Your Week 10 choices

On November 16 you reported choosing **Over on all three** printed games. They are recorded with the actual report timestamp; the original placement time is unknown. Your record is **1–2**: MIN/GB and SEA/LV lost; PIT/CIN won. The model has **zero** picks for that printed card. Your choices carry no invented probabilities.

## Optional three-game printed card

Each week the user supplies the three matchups and their exact printed totals, usually from a brochure photo. They choose the games; the model does not automatically select three. Preserve the printed lines even if online prices differ.

`data/cards/2026-week10.json` transcribes the attached Week 10 William Hill NFL Progressive Card:

| Game | Printed line | Final combined score | Result |
|---|---:|---:|---|
| MIN at GB | 42.5 | 40 | Under |
| SEA at LV | 43.5 | 34 | Under |
| PIT at CIN | 47.5 | 56 | Over |

The image was provided after those games finished. `received_at` is unknown, and there are no saved pregame total-points forecasts for them. They are **historical results**, with zero evaluated model O/U picks, not three retroactive wins or losses. The brochure's reverse/settlement terms were not supplied; this tracker compares combined final score to the printed number and does not implement pool payout or entry rules.

For a future week, create a new `data/cards/SEASON-weekWEEK.json` with `season`, `week`, exact offset-aware `received_at`, `source`, and exactly three distinct `games`, each containing `event_id`, `home`, `away`, `line`. Use ESPN event IDs and canonical team codes from the reviewed schedule. Verify the year/week, teams, half-point transcription and source before release. Do not invent a historical receipt timestamp. The dashboard/server defaults to the matching card file, or accepts `--card PATH`.

## Separate total-points model

```powershell
python -m nfl_predictor research-totals --dataset data/snapshots/dataset-v4-2026-11-16.json.gz --venues data/snapshots/venues-v4-2026-11-15.json --season 2026 --week 10 --output work/new-totals-research
```

The winner model's probability does not predict a total. This separate ridge regression uses prior offense/defense/QB quality, pace, pass/explosive/sack tendencies and candidate weather/injury/body-clock context. Penalties are tuned on rolling 2024 MAE, families selected on 2025 MAE, and 2026 Weeks 1–9 labeled previously examined diagnostics. Tied NFL games still have valid total points and are included. Training-only imputation/standardization is retained.

Out-of-week 2024 residuals produce an empirical integer-score distribution and 80% predictive range. The selected context model's 2025 interval coverage was **76.8%**, below nominal 80%; probabilities/ranges remain experimental. Historical brochure lines with reliable timestamps are unavailable, so total-score error does not establish over/under accuracy or a betting advantage.

Add `--totals-model PATH/totals-model.json` to the normal `forecast` command after a fresh `prepare` and `check`. Hashes and cutoff must agree with winner research/preparation. It saves the total projection alongside each new pregame prediction. Week 10's Monday projection was saved before kickoff; it is not one of the three printed O/U games.

When the brochure line and forecast both have valid pre-kickoff timestamps, the dashboard can show Over/Under probabilities and a lean. Half-point lines have no push; whole-point pushes are separate. The empirical distribution receives small category smoothing to avoid zero probabilities. Do not multiply three individual probabilities to claim a perfect-card probability; game dependence and pool rules are not modeled.

```powershell
python -m nfl_predictor score-card --card data/cards/2026-week10.json --forecast reports/2026-11-16-complete/monday-with-totals/forecast.json --results data/snapshots/week10-results-2026-11-16-morning.json --output work/new-card-score.json
```

Scoring uses exact saved forecasts and lines, rejects mismatched weeks and counts pushes, pending and unavailable predictions separately. Brier/log loss and pick accuracy condition on a non-push result. Save new weekly configuration and forecast/review files to Git; do not rewrite an earlier card to match outcomes.

An exact 50/50 over/under estimate is **No lean**, not a directional pick. It has `correct: null`, is excluded from the directional pick metrics, and appears separately in `abstentions`. Both the cards and summary use this policy.
