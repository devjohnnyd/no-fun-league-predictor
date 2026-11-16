# Personal NFL predictor

This is a personal research repository owned by `devjohnnyd`. Use ordinary Python conventions; company, Exostar, SCP Dev and RMOS workflows do not apply.

- Keep archived forecasts and delivered workbooks unchanged. Score them using their original probabilities. Create a new timestamped batch for later forecasts.
- Refresh and inspect pregame injuries, projected QB, team/QB statistics, coaches and kickoff weather. Check official inactive lists close to kickoff. Use `python -m nfl_predictor check` before issuing picks; unresolved required inputs block release.
- Never generate a new prediction for a game that has started. Do not use postgame injuries, observed game weather, actual lineups or target-game statistics as if they were known before kickoff.
- New metrics are experimental until earlier-season evaluation and future timestamped results support promotion. Do not select changes by whether they flip three known losses.
- Missing data are unknown. Do not silently replace an unavailable QB, injury report or weather forecast with a healthy/average/calm observation.
- Use Brier score and log loss alongside pick accuracy. Keep ties, pending and unavailable results separate from decisive games. Describe retrospective and live results separately.
- Store source URLs, retrieval timestamps, checksums and exact data cutoffs. Cached imports retain their original cutoff; importing them today is not a new source retrieval.
- Run `python -m unittest discover -s tests -v` for code changes. `python -m nfl_predictor evaluate --output <new-directory>` verifies chronological comparisons and reproduces v2.
- The user requested this work be committed here. Keep credentials, virtual environments, generated caches and raw bulk downloads out of Git. Verify the remote is `https://github.com/devjohnnyd/no-fun-league-predictor.git` and the repository-local identity is `devjohnnyd` before committing/pushing. Do not modify global Git identity or rewrite published history.
