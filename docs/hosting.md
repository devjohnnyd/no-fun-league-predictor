# Dashboard hosting

The site is built locally for separate hosting. No external site was published and no recurring job was installed.

## Build and run with live scores

From the repository root, install Python dependencies with `python -m pip install -e .`, then:

```powershell
npm ci --prefix web
npm --prefix web run build
python scripts/configure_dashboard.py --snapshot data/snapshots/dashboard-week10-release-2026-11-16.json --complete --copy-assets
python -m nfl_predictor serve --season 2026 --week 10 --metadata data/snapshots/venues-v4-2026-11-15.json --dataset data/snapshots/dataset-v4-2026-11-16.json.gz --forecast archive/session-2026-11-10/enhanced/model.json --forecast reports/2026-11-16-complete/monday-with-totals/forecast.json
```

Use Python 3.11+ and Node 22.12+ (24 recommended). Configure the reviewed snapshot **before building** when changing data; `--copy-assets` after building copies all logos. The committed `web/src/data.json` is already the complete Week 10 view. `web/dist` is generated, not committed.

Open http://127.0.0.1:4173/. Browser requests use `./live-week.json` every 60 seconds while visible; manual refresh uses the same endpoint. The server validates season/week and caches successful requests for 30 seconds. Provider failures return 503, preserve displayed rows and source time, and show a warning. `/api/health` reports season/week. Scores update independently of saved forecasts.

For your hosted website, serve `web/dist` and proxy same-origin `live-week.json` to this backend. Keep the backend on a private interface behind your normal HTTPS web server. The Python server is a local/small-use reference, not a production authentication/TLS system. No provider keys reach browsers.

## Static-only hosting

```powershell
python scripts/package_dashboard.py --snapshot data/snapshots/dashboard-week10-release-2026-11-16.json --output dist/no-fun-league-week10.zip
```

Upload the archive's `index.html`, `live-week.json` and `team-logos` together to a directory served over HTTP(S). The included JSON is dated; it does not become fresh just because a browser reloads it.

For live static hosting, a scheduled process/serverless job can run `scores`, then `export-week` with saved forecast batches into a **new temporary file**. Atomically replace hosted `live-week.json` only after validation succeeds. Return `Cache-Control: no-store` (or max-age ≤30 seconds), preserve the actual provider retrieval time and match the dashboard's season/week. The exporter/data contract are supplied; deployment and refresh scheduling depend on your host and are not configured here.

```powershell
python -m nfl_predictor export-week --manifest data/raw/current-scores.json --metadata data/snapshots/venues-v4-2026-11-15.json --dataset data/snapshots/dataset-v4-2026-11-16.json.gz --forecast archive/session-2026-11-10/enhanced/model.json --forecast reports/2026-11-16-complete/monday-with-totals/forecast.json --output work/live-week-next.json
```

Changing weeks requires new inputs, forecasts and a rebuilt snapshot; the app rejects a different week's feed. Add saved forecast revisions by restarting the Python server with an extra `--forecast` path. The app retains source inspection, themes, export and local presentation tools. Browser-specific presentation edits never modify saved forecast files or the repository.
