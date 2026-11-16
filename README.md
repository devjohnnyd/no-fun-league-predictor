# No Fun League Predictor

An NFL game tracker and probabilistic winner model. It combines quarterback and team efficiency, player availability, coaching context, rest and weather.

The November 10, 2026 forecasts and original analysis are retained as an audit baseline. Improvements are evaluated chronologically before they are used for new games. Forecasts are estimates conditional on a decisive result. Ties are tracked separately.

## Baseline

- 2026 retrospective Model 2 results through Week 9: 90 correct picks in 135 decisive games (66.7%).
- Historical injury reports lack complete publication timestamps. Historical weather inputs are observed conditions. Those checks are exploratory and do not establish prospective accuracy.
- The first live forecast batch was issued November 10 for November 15–16. New model versions must not rewrite those forecasts.

Archived scripts and snapshots are in `archive/session-2026-11-10/`. The delivered workbook is in `reports/2026-11-10/`.

Public source downloads and local runtime dependencies are excluded from Git. Source URLs, derived analysis and forecast snapshots are versioned.
