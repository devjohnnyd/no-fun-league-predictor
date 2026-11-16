# Background market collection

The hosted API runs market collection as a separate lifespan service. It does
not require the dashboard, the owner's computer, a William Hill card, or a
successful model preparation. It uses the existing ESPN-listed provider totals;
these are not the William Hill Progressive contest's fixed printed totals.

## Cadence

The service checks nearby schedule weeks, including Thursday/international
games, at startup and every 30 seconds for due work. A week enters collection
when a scheduled kickoff is within eight days. Collection continues for recent
games awaiting finals (up to 12 hours after their scheduled kickoff).

After each successful fetch, schedule the next check according to the nearest
future kickoff or live game in that week:

- More than 24 hours away: 15 minutes.
- Within 24 hours: five minutes.
- Within two hours or while any game is live: one minute.
- All games confirmed final: stop that week's collection.

The existing 30-second server feed cache is shared with dashboard readers and
model preparation. A reused response keeps its exact source time; a collector
attempt is not a new source retrieval. A changed kickoff is reflected on the
next complete, validated scoreboard fetch. Missed polls are not backfilled.

## Evidence and failures

`market-collection.sqlite3` in `NFL_STATE_DIR` retains per-week attempt, success,
quote and next-due times, coverage counts, failure state and a two-minute lease.
A new process respects that lease and recovers after expiration. Network work
runs outside database transactions. Provider failures retry after one minute,
doubling up to 15 minutes; other weeks continue independently.

Every valid pregame quote retains provider identity, total, retrieval time, source
URL/hash, and the saved pregame forecast used for its analysis in `lines.sqlite3`.
No quotes or new picks are recorded after kickoff. Live/final polling only
refreshes scores and settlement. Original picks always settle against their
original lines, and provider changes do not count as same-provider movement.

Missing quotes retain the last observed line, its original timestamp and the
original pick. They do not receive a current lean. A successful source check
and a successful pregame quote capture have distinct times and coverage counts.
The dashboard shows these in **Background lines**. Source coverage can be
partial even when the service is running normally. Quotes may be delayed by
the provider; first/last observed is not guaranteed market open/close.

All observations remain in SQL. Visible game history includes line/analysis
changes and each provider's latest check, with the full observation count.
Repeated unchanged checks do not inflate the mobile response/history display.

## Hosting and configuration

Continue using the existing single-worker, single-instance Azure app with Always
On and persistent `/home/nfl-tracker`. No new service, credentials or subscription
is required. `NFL_MARKET_COLLECTION_ENABLED` overrides the preparation setting;
by default it follows `NFL_AUTOMATION_ENABLED`. For market-only local testing,
set preparation to `0` and market collection to `1`, with an isolated state path.
Set both to `0` for previews without background provider requests.

The hosted API starts the collector. The local `python -m nfl_predictor serve`
command does not, so its dashboard shows **Background lines · Off**; local line
history then grows only from dashboard reads and manual refreshes.

GET `/nfl/api/refresh` returns `marketCollection` alongside preparation status.
The collector never trains models. Fresh line analysis still uses the saved
projection's actual issuance time; refreshing a line does not make model inputs
current. A card released later in the week can be added separately.
