# Season performance

Status: implemented for review; the production bundle has not been regenerated or deployed.

Open `/?page=performance` on the running predictor server. The hosted wrapper is prepared at `https://www.johnnyd.ai/nfl/performance/` and reads `/nfl/performance.json` from the API after the reviewed bundle is deployed. The existing Data app identity, source inspection, editing, chart menus and theme remain intact. This route remains unlisted and public.

## What enters the record

- **Winner picks:** one earliest saved forecast per game across the immutable loaded batches. The original probability is scored. Later revisions appear in the ledger separately, with their issue time; they never rewrite the original record. Duplicate copies do not add games. Date-only legacy issue times remain explicitly date-only and must conservatively establish a pregame release.
- **Market totals:** the first tracked directional analysis for each game, at that observation's exact sportsbook and line. Earlier quotes without a forecast are not treated as predictions. A 50/50 analysis is an abstention; later directional choices can start the original directional record. Ties between simultaneous providers use stable provider-ID ordering. This is a model pick record, not evidence of a placed wager.
- **Printed card model:** only exact-line picks saved in a pregame forecast's `total_pick`, validated against the printed line, predictive distribution and line-received timestamp. A timely projection alone never creates a scored historical pick.
- **Your printed card picks:** user-reported Over/Under choices, graded separately. Choices reported after kickoff are flagged; actual placement times are unknown. No model probabilities or probability scores are assigned to these choices.

Previously completed weeks without recorded forecasts are unscored. Historical model backtests are excluded. The new William Hill card and recent reference photos are not imported by this feature.

## Metrics and coverage

Accuracy is wins divided by decisive picks. Winner ties, total pushes, pending games, abstentions, missing picks and unavailable results are separate counts. An empty record has null accuracy, not zero accuracy. Brier score and log loss use saved home-win / Over probabilities on decisive outcomes only; totals probabilities condition on no push. Season metrics weight games, rather than averaging weekly rates. Lower probability scores are better.

Filters select record type and week. Weekly tables show tracked weeks; weeks without picks remain unscored. Confidence bands compare mean predicted chance with actual hit rate and include sample sizes. The first dozen settled predictions are a small sample, not proof of reliable calibration or an edge. No perfect-card probability or expected profit is claimed.

The ledger preserves original choice, provider, exact line, source issue precision, forecast checksum, result receipt and latest winner revision. Native source inspection exposes the reviewed rows and scoring policy.

## Read-only refresh

The performance endpoint reads immutable forecast files, the existing printed-card files and the append-only quote ledger. It fetches ESPN result scoreboards directly; it does not call quote enrichment, append observations, trigger preparation or fit models. A streaming SQLite query selects original market picks without retaining the entire observation history in memory.

The payload is cached for 60 seconds. Pending-week scoreboards are reused for 60 seconds and fully completed weeks for an hour. The displayed oldest results-check time is the original provider retrieval time, separate from report generation time. Provider failure retains an earlier validated result with a warning and its original timestamp; initial failure leaves results unavailable. Full-slate identity validation rejects missing, duplicate or conflicting events. Invalid or late saved predictions fail closed.

Standalone endpoint: `/performance.json`. Hosted API endpoint: `/nfl/performance.json`. Both return an explicit service error when report assembly fails, leaving existing saved picks unchanged. Browser refresh validates scope, distinct selections, weekly coverage and metric reconciliation before replacing the displayed report; a failed refresh retains the last successful display.

## Verification and handoff

Run `python -m unittest discover -s tests -v`, `node --test tests/*.test.mjs` and the protected-runtime-verified web source build. Host integration uses its API tests and Astro check/build. Browser QA covers record/week/status filters, empty selections, source details, native component actions, the original games page and narrow viewports.

For the November 16 local preview, `work/preview_performance.py` uses a SQLite backup under `work/performance-preview/`, not production state. The observed original winner record was 9-3 with one pending game; the quote count stayed at 210 across performance reads. The three supplied user choices were 1-2 and reported after kickoff. These are a point-in-time local verification, not a deployment claim.

To release, regenerate the johnny-ai API bundle with `scripts/sync_portfolio.py`, deploy the API, then push the host `web/**` change (that push triggers the Static Web Apps deployment). Deploy both together: the Games and Performance links 404 until the host page is live.
