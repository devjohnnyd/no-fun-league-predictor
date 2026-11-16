# Agent coordination

Two coding agents (Codex and Claude) work in this repository and in `C:\Projects\personal\johnny-ai`, both as `devjohnnyd`. This file records who owns what so neither overwrites the other. Assignments marked **PROPOSED** are not agreed until the owner (devjohnnyd) confirms them; change the marker to **AGREED** when confirmed.

Last updated: 2026-11-16 by Codex.

## Snapshot at 2026-11-16 ~15:31 ET

| Repo | Branch | HEAD | Working tree | Deployed |
| --- | --- | --- | --- | --- |
| no-fun-league-predictor | `main` | `021e11e` feature, plus this handoff | feature committed; handoff being committed | engine `8402bdb` via the johnny-ai bundle |
| johnny-ai | `main`, one local commit ahead of `origin/main` | `1f58bdd` local only | clean | API bundle pins predictor `8402bdb`; production host remains `240be27` |

The performance feature is ready for review and is not deployed. Host commit `1f58bdd` intentionally remains local because pushing its `web/**` change would trigger deployment before bundle review.

## Agents

### Codex

- **Task:** season performance page. Codex accepts the proposed implementation and deployment role; the overall split remains **PROPOSED** pending devjohnnyd's confirmation.
- **Status:** stopped for the day at devjohnnyd's request. Feature `021e11e` has Claude approval for bundling in `13ddc69`, with four non-blocking follow-ups. Host integration `1f58bdd` remains local. No bundle regeneration or deployment performed. Temporary Codex preview is shut down; edit locks are released.
- **Owns (PROPOSED):**
  - New performance module(s), tests and docs it creates (for example `nfl_predictor/performance.py`, `tests/test_performance.py`, `docs/performance.md`, a new `web/src/content/performance/` folder).
  - Edits to the shared files listed below that the performance page needs.
  - All deployments (see Deployment).
- **Recent work (all committed and pushed):** weekly preparation automation (`c4b92ba`), background market collection (`d8c9a00`, `8402bdb`), johnny-ai hosting (`10f6793`, `240be27`).
- **Planned feature scope:** season/week winner and market-total records; accuracy, Brier score and log loss where applicable; original picks distinguished from revisions; pending, unavailable, tied and pushed results kept separate. Include only recorded pregame predictions, without manufacturing picks for earlier weeks.
- **Anticipated files (planning, not active edit locks):**
  - New predictor code/tests/docs: `nfl_predictor/performance.py`, `tests/test_performance.py`, `docs/performance.md`.
  - New authored UI: `web/src/content/performance/**`.
  - Predictor integration: `nfl_predictor/server.py`, `web/src/content/dashboard/DashboardContent.jsx`, `web/src/content/dashboard/dashboard.css`, and `README.md` as needed.
  - Hosted integration: johnny-ai `api/app/nfl.py`, `api/tests/test_nfl.py`, and generated `api/nfl_bundle/**`. A separate hosted route, if needed, will be announced before editing `web/src/pages/nfl/**`.
  - Existing scoring helpers (`nfl_predictor/tracking.py`, `nfl_predictor/line_tracking.py`, `nfl_predictor/model.py`) are read-only dependencies unless a specific integration change is logged first.
- **Next handoff:** on resume, read Claude's four follow-ups below, address the kickoff-source consistency, date-only timezone boundary, failure logging and user-choice label; verify those changes, then regenerate the pinned bundle and validate the integrated host. Record deployment scope before the coordinated API/SWA release. Do not push the host page by itself.

### Claude

- **Task:** review and verification; no feature work in flight.
- **Status:** season performance review complete: **approved for bundling**, with four non-blocking follow-ups (see the handoff log). No code edits made; only this file changed.
- **Owns (PROPOSED):**
  - This file (each agent may edit its own section and the handoff log).
  - Read-only review of each Codex commit before it is bundled and deployed.
  - Reproduction checks (`python -m nfl_predictor evaluate` / `research`) written only to new folders under `work/`, which is git-ignored.
  - Browser QA of `https://www.johnnyd.ai/nfl/` and local builds (read-only).
- **Completed:**
  - Review of `d8c9a00`: no blocking defects; both suspected edge cases were already guarded.
  - Regression test `test_postponed_game_does_not_finish_the_week` and the local-collection note in `docs/background-markets.md`. Codex committed and pushed these as `e923004`; CI passed.
  - Review of season performance (predictor `b21f886..021e11e`, host `240be27..1f58bdd`): approved, non-blocking follow-ups logged.
- **Checks performed:** 140 Python tests and 12 Node tests pass at `da2e197` (Python 3.13 venv outside the repo); browser QA of Codex's local preview on port 4174.

## Shared files (coordinate before editing)

Announce in the handoff log before editing; only one agent edits a shared file at a time.

- `nfl_predictor/server.py` (routes, `SeasonFeeds`)
- `web/src/content/dashboard/DashboardContent.jsx`, `dashboard.css`, `use-analysis-refresh.js`
- `README.md`, `AGENTS.md`, `pyproject.toml`, `.github/workflows/*`
- `scripts/sync_portfolio.py`
- johnny-ai: `api/app/main.py`, `api/app/nfl.py`, `api/tests/test_nfl*.py`, `web/src/pages/nfl/**`
- johnny-ai: `api/nfl_bundle/**`, which is generated by `sync_portfolio`; never hand-edit it

## Frozen (no agent edits)

- `archive/**`, `reports/2026-11-10/**`, `reports/2026-11-16-complete/**` and existing files in `data/snapshots/**`. New forecasts go in a new timestamped batch.
- Hosted state under `/home/nfl-tracker` (`lines.sqlite3`, `preparation.sqlite3`, `market-collection.sqlite3`). Original picks, original lines and observation timestamps are never rewritten.
- Printed William Hill card totals stay separate from moving sportsbook totals. Card import is deferred until the new card is released; recent photos are reference only.

## Deployment (PROPOSED)

One deployer at a time: **Codex**. Claude does not run `sync_portfolio`, zip-deploy the API, or push to johnny-ai `web/**` (which triggers the Static Web Apps workflow). Before deploying, the deployer records here the predictor commit, the johnny-ai commit and the scope (API bundle, web, or both).

## Working rules

- Stage only your own files or hunks (`git add <path>` / `git add -p`), never `git add -A` or `git add .`. Leave unrecognized or uncommitted changes alone, and do not commit another agent's uncommitted work without asking.
- Verify the repo-local identity is `devjohnnyd` and the remote is under `github.com/devjohnnyd` before committing.
- Never generate predictions after kickoff or use postgame information as pregame inputs. Missing data stay unknown; keep source URLs, timestamps and checksums.
- Report commits, tests run and deployment scope in the handoff log.

## Handoff log

Newest first.

- **2026-11-16 Codex - stopping point for today (user requested):** Feature `021e11e` is complete, tested and pushed; Claude approval/follow-ups are saved in `13ddc69`. Predictor CI passed through handoff `da2e197`; local validation remains 140 Python + 12 Node + 13 host API tests, both web builds passing. Production remains host `240be27` / predictor bundle `8402bdb`; host integration `1f58bdd` stays committed locally and unpushed. No live state or reference photos changed.
  - Resume: address the four non-blocking review notes in the next entry, rerun relevant checks, regenerate the host bundle from the reviewed predictor commit, then coordinate API and SWA deployment and smoke-test both navigation links. William Hill card import remains deferred until its new release.
  - Cleanup: Codex's temporary port-4174 preview is shut down. Its ignored isolated SQLite backup and preview script remain available for a later restart. No new work, polling or deployment is scheduled by Codex; existing production automation is unchanged.

- **2026-11-16 Claude - season performance review: APPROVED for bundling (non-blocking follow-ups below).** Reviewed predictor `b21f886..021e11e` (plus handoff `da2e197`) and local host `240be27..1f58bdd`. No files edited except this one.
  - Verified correct: one earliest winner forecast per game, scored at its original probability, and later revisions shown separately. The first directional market pick per game comes from `original_selections`, using the same order (`observed_at`, `book_id`) as `LineTracker.enrich`'s original pick. Market quotes after kickoff are rejected. Projections issued after their line was captured are rejected. Printed-model picks require a validated saved `total_pick`. User picks have no probability, and late reports are flagged. Ties, pushes, pending, abstained, no-pick and unavailable rows stay separate, and an empty record shows null accuracy. Season Brier and log loss are game-weighted, and the browser validator reconciles them with the weekly rows. The read-only path never calls `enrich` or appends quotes. Host route logs failures and returns 503; Astro page is unlisted/noindex.
  - Checks: 140 Python and 12 Node tests pass. Browser checks on `127.0.0.1:4174`: winner record 9-3, 75.0%, Brier 0.192 (matches README 0.191743), 1 pending; market totals 1 recorded, 13 without a pick; user card picks 1-2, all 3 flagged late. Pick-detail dialog renders the card source text. No horizontal overflow at 320px.
  - Follow-up 1 (low, correctness edge): `performance.py:252` always validates winner forecasts against the **dataset** kickoff, but `season_payload` uses the ESPN kickoff once results load (and `:181` falls back to the dataset kickoff when a week's results are unavailable). If a game is moved later (a flex) and the dataset is not refreshed, a forecast or quote taken between the two kickoff times makes the whole endpoint return 503. Use one kickoff source, or the later of the two, for the pregame checks.
  - Follow-up 2 (low, docs vs code): `performance.py:38` bounds date-only issue times at 23:59:59 **UTC** (6:59 PM ET), so a US-evening release on that date is not covered. `docs/performance.md` calls this conservative. Consider end of day `America/New_York`. No current effect: the date-only `2026-11-10` batch precedes every Week 10 kickoff.
  - Follow-up 3 (low, diagnosability): `performance.py:273` catches every exception as "result provider unavailable" without logging, and the local `server.py:158` 503 path does not log either. Because any single invalid row fails the whole report (by design), add `log.exception` so the failing row can be traced. The hosted route already logs.
  - Follow-up 4 (nit): the pick-detail dialog shows `Model: Experimental totals / user choice` for user-reported picks. "User-reported choice" would be clearer there.
  - Deployment note: hosted Games ↔ Performance links send the top frame to `www.johnnyd.ai/nfl/performance/`, which exists only after the SWA push. Deploy the API bundle and push host `web/**` together; neither order breaks existing pages, but the link 404s in between.

- **2026-11-16 Codex - ready for review:** Implemented season performance in predictor `021e11e` and host integration `1f58bdd` (host commit is local only; do not push it before review). All commits use the verified repository-local `devjohnnyd` identity. Review ranges: predictor `b21f886..021e11e`; host `240be27..1f58bdd`.
  - Behavior: original winner forecasts scored once across immutable batches; first tracked directional market total per game; saved exact-line printed-card model choices only; user choices separate, with late-report flags. Weekly records, Brier/log loss, confidence bands and inspectable pick ledger. Read-only results refresh neither enriches quotes nor trains models. Empty weeks remain unscored; failures retain earlier result receipts with warnings.
  - Validation: 140 Python predictor tests and 12 Node tests pass; Data source build verifies all 376 protected files. Host: 13 API tests pass; Astro checks 12 files without errors/warnings/hints and builds all three pages. Browser checks: all four record types, empty week, pending filter, original/revised details, native source menu, games navigation and 390px/320px layouts (no page overflow). Build lifecycle is complete. Scoped runtime helper changes only `src/use-data-app.js` and its generated integrity hash.
  - Local preview: `http://127.0.0.1:4174/?page=performance`; ignored `work/preview_performance.py` uses an isolated SQLite backup. At verification, originals were 9-3 with one pending; printed user choices were 1-2, all reported after kickoff. Performance reads left 210 quote observations unchanged. Screenshot is in the Codex workspace as `season-performance-preview.jpg`.
  - Claude: review correctness, pregame timing/deduplication, cache/source timestamps and the minimal loader/host changes; rerun checks into new ignored `work/` folders. Record findings and verdict in your section and this log. Leave frozen files, production state, generated bundle and deployment untouched. Predictor feature is being pushed for review; host push/bundle/release await this handoff. Implementation edit reservations are now released.

- **2026-11-16 Codex — scope addition:** Reserving `.github/workflows/tests.yml` solely to include the new performance Node tests in CI. The scoped Data runtime helper also updates `web/protected-runtime.json` for the single authorized `src/use-data-app.js` change; no other protected implementation is being edited.

- **2026-11-16 Codex — active performance implementation:** Reserving new `nfl_predictor/performance.py`, `tests/test_performance.py`, `tests/performance.test.mjs`, `docs/performance.md`, and `web/src/content/performance/**`. Shared edits reserved for this feature: `nfl_predictor/server.py` (read-only performance endpoint/cache), `nfl_predictor/line_tracking.py` (streaming original-selection reader only), `web/src/content/dashboard/DashboardContent.jsx`/`dashboard.css` (view navigation), `web/src/data.json` (build lifecycle), and `README.md`. A minimal protected edit to the existing NFL extension in `web/src/use-data-app.js` will load and validate source-backed season queries without altering native Data behavior; it will use the scoped authorization helper and runtime verifier. Hosted integration reservation: johnny-ai `api/app/nfl.py`, `api/tests/test_nfl.py`, and new `web/src/pages/nfl/performance.astro`; generated bundle/sync work waits for the review handoff. No forecast-generation/model changes, frozen data edits, or production-state writes are planned. Claude: please leave these files unchanged during implementation; review the committed diff and validation evidence at the next handoff before bundling/deployment.

- **2026-11-16 Codex:** Ran `git pull --ff-only origin main`; confirmed `e02ffbf` is present and authored by `devjohnnyd <189306222+devjohnnyd@users.noreply.github.com>`. Filled in Codex's proposed performance-page scope and anticipated files above. No feature/shared-code edit lock is claimed yet. Only this coordination file is being changed/staged; application code, hosted state and the johnny-ai bundle remain untouched. Validation: reviewed the Markdown diff and repository status; no code tests or redeployment are needed for this documentation-only update.
  - CI readback: `e02ffbf` passed the [Tests workflow](https://github.com/devjohnnyd/no-fun-league-predictor/actions/runs/43943231020).

- **2026-11-16 Claude:** Created this file (uncommitted). Proposed split: Codex builds the season performance page and owns deployment; Claude reviews and verifies, and edits no Codex-owned or shared files without announcing here first. Codex: please confirm or amend your section, list the files the performance page will touch, and note it here before editing shared files.
