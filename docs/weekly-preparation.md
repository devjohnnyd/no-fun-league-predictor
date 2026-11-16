# Weekly preparation

The hosted johnnyd.ai API starts the preparation service through FastAPI's
lifespan. It runs without an open dashboard or the owner's computer. The existing
Azure App Service must retain Always On, one instance and one uvicorn worker.
`NFL_AUTOMATION_ENABLED=0` disables startup; manual refresh remains available.
This is application code on the existing Azure host, not a Codex desktop task.

## Cadence and release gates

- Check the schedule every minute. Prepare upcoming weeks within seven days,
  including Thursday, international games, Sunday and Monday.
- Prepare statistics/models once per UTC day when a future game exists. On
  startup, catch up immediately. Incomplete prior-week results/play-by-play block
  release and retry hourly, with at most six full preparations per UTC day shared
  with manual refresh. Manual full preparations also have a ten-minute cooldown.
- At six hours before each kickoff group, refresh QB/depth, injury reports,
  coaches and kickoff weather using verified fitted artifacts under 24 hours old.
- At 90 and 30 minutes before kickoff, run final checks. Missing official inactive
  lists for either team or an unverified retractable-roof decision block a final
  release. Failed checks retry every ten minutes in their window. The six-hour
  window ends at 90 minutes; the 90-minute window ends at 30 minutes; the last
  window ends five minutes before kickoff.
- Final inactive verification is still reviewed evidence, not an automated
  official-feed integration. ESPN injury coverage is never called an official
  inactive list. Existing `pregame-review.json` under the state directory can
  supply the already-supported, event-specific reviewed source receipts.
- Fit before preparing the live feature vector. Issue-time identity, live state,
  feature age, source ages and exact model/data cutoffs are checked again. Never
  issue for a started game. Old forecasts remain immutable.

If statistics are ready but another input blocks release, retry the context
using the saved models instead of fitting again. Partial releases keep the
blocked games visible and eligible for retry. Each check stores exact source
receipts, reasons and a new forecast batch when permitted.

## State and recovery

State lives under `NFL_STATE_DIR` (`/home/nfl-tracker` on Azure):

- `preparation.sqlite3`: daily/pregame job keys, attempts, results and a five-minute
  coordinator lease. A replacement process waits for the lease and reconciles
  saved run IDs; interrupted jobs become eligible for retry.
- `refresh-budget.json`: shared full-preparation budget across restarts.
- `refreshes/<timestamp>/`: immutable datasets, research/models, prepared context,
  release or blocked receipts and final status. Context-only releases reference
  their exact cached dataset by checksum. Hash mismatch/expired caches block use.

The browser reads `/nfl/api/refresh` for live job and automation status. Game
details show each input's source and age; completed games use age at forecast
issuance. A successful score refresh does not refresh model-input timestamps.
[Background market collection](background-markets.md) runs independently of
model preparation, so quotes can still be gathered while statistics are blocked.

Manual checks: run the core Python and Node tests, validate the bundle's hashes,
start the API with an isolated state directory, and read health/status/feed.
After deployment, verify the scheduler is enabled and the next job and last
attempt are visible. Use UTC event keys and IANA Eastern schedule conversion;
never infer the NFL week from a weekday number alone.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Azure Always On](https://learn.microsoft.com/en-us/azure/app-service/configure-common).
