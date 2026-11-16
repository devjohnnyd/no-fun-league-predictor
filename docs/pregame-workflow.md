# Pregame workflow

The November 10 workbook is a frozen forecast, not a live feed. `refresh` collects new evidence; it does not rebuild the historical feature matrix or automatically publish a new prediction. The v3 fitted model is a research candidate. The v2 forecast record remains the live baseline.

## Friday / preliminary forecast

1. Use a new dated folder for every refresh, for example:

   ```powershell
   python -m nfl_predictor refresh --season 2026 --week 11 --output data/raw/2026-11-20-week11
   ```

2. Rebuild current team/QB efficiency from completed previous weeks. Reconcile schedule results with play-by-play coverage. Preserve the cutoff and source hashes. The current portable evaluator intentionally reproduces the November 10 snapshot; its inputs are not current for Week 11.
3. Inspect both teams' depth charts, recent transactions and injury reports. Record the projected starting QB and uncertainty. Examine center/tackle absences and recent offensive-line continuity. A player without recent snaps is not automatically an unimportant absence.
4. Verify head coach, offensive coordinator and defensive coordinator against official team pages. A new coordinator is context until a supported historical feature exists. Prior QB dropbacks with a head coach do not prove familiarity with a different coordinator's scheme.
5. Obtain weather near kickoff. The collector prefers venue coordinates; otherwise it requires a unique exact city/country/state geocoding match and explicitly labels city-level conditions as a proxy. Ambiguous matches remain missing. Record temperature, sustained wind, gusts and precipitation. For a retractable roof, verify the roof decision or retain open/closed scenarios. Outdoor forecasts alone do not confirm a roof decision.
6. Add reviewed evidence to a new copy of the refresh manifest. Every source carries `event_id`, `url`, `status: "ok"` and offset-aware `retrieved_at`. Statistics additionally carry `season` and `through_week`, which must be exactly the previous week. Weather carries `valid_at`, `temperature_f` and `wind_mph`, or `enclosed_verified: true` with supporting evidence. A single source receipt may summarize separately linked evidence for both teams; retain both receipts.
7. Run the preflight for the intended game:

   ```powershell
   python -m nfl_predictor check --manifest data/raw/reviewed-manifest.json --event 401873065
   ```

   Missing or stale required data produce exit status 1. By default the command checks pending Sunday/Monday games. An explicit event also rejects a game already in progress or final. The manifest and the feature inputs must refer to the same game and cutoff; a refreshed manifest does not refresh an old feature vector.

## Final check about 90 minutes before kickoff

Refresh injuries, depth and weather. Verify official inactive lists for **both teams** and reconcile them with the projected QB and OL. Record the official URLs, `official: true`, `verified_teams: ["HOME", "AWAY"]` and the review time in `sources.inactives`. These are reviewed evidence fields, not an automatic assertion that ESPN depth charts are official inactive lists.

```powershell
python -m nfl_predictor check --manifest data/raw/reviewed-manifest.json --event 401873065 --final
```

Final checks must occur in the two hours before kickoff; injury/depth/inactive evidence must be at most two hours old and weather at most six. Preliminary limits are 24 hours for injury/depth, 12 hours for weather, 48 hours for statistics and seven days for coaching context. These are operational defaults, not learned football effects. Rebuild features after any lineup change, compare QB/roof/availability scenarios and save the new forecast's exact `issued_at`, model version, sources and probabilities. Never relabel a later forecast as the original pick.

## After games

```powershell
python -m nfl_predictor score --forecast archive/session-2026-11-10/enhanced/model.json --results data/snapshots/week10-results-2026-11-16T0155Z.json --output reports/week10-new-score.json
```

Scoring writes a new file and rejects an existing output path. It separates decisive games, ties, pending games and missing results; it also records probability calibration bands and expected losses. The original batch only records a November 10 issue date. New batches should record an exact timestamp. Do not count an unfinished game as a win or loss.

There is no scheduled background refresh. Run these checks for each batch and before kickoff. A reusable current-season feature builder and timestamped shadow forecasts are the next step before any v3 candidate replaces the live baseline.
