import React, { useEffect, useMemo, useState } from "react";
import { Button, DataComponent, Dialog, Dropdown, Icon, SegmentedControl, SortableItem, SortableRegion, useDataApp } from "../../data-app-public.jsx";
import { filterGames, gameSummary, kickoffLabel, orderedGames, predictionLabel, sourceAgeLabel } from "./football.mjs";

function TeamRow({ row, side }) {
  const opponent = side === "home" ? "away" : "home";
  const winner = row.state === "post" && row[side + "Score"] > row[opponent + "Score"];
  return <div className={`nfl-team ${winner ? "is-winner" : ""}`}>
    <span className="nfl-logo-well"><img src={row[side + "Logo"]} alt={`${row[side + "Name"]} logo`} width="46" height="46" loading="lazy" /></span>
    <div className="nfl-team-identity"><span className="nfl-team-name">{row[side + "Name"]}</span><span className="nfl-team-code">{row[side + "Code"]}{side === "home" ? " · Home" : " · Away"}</span></div>
    <span className="nfl-score" aria-label={row[side + "Score"] == null ? "Not started" : `${row[side + "Score"]} points`}>{row[side + "Score"] ?? "—"}</span>
  </div>;
}

function GameCard({ row, onDetails }) {
  const label = row.state === "in" ? "Live" : row.state === "post" ? "Final" : row.state === "pre" ? "Upcoming" : row.statusDetail || "Status unavailable";
  const confidence = row.pickProbability == null ? null : Math.round(row.pickProbability * 100);
  const color = row.pick === row.homeCode ? row.homeColor : row.awayColor;
  const teamColor = /^[0-9a-f]{6}$/i.test(color || "") ? `#${color}` : "var(--accent)";
  return <article className={`nfl-game ${row.state === "in" ? "is-live" : ""}`} data-testid="game-card" data-event-id={row.eventId} data-reviewed-rows>
    <div className="nfl-game-top"><span className={`nfl-status state-${row.state}`}>{row.state === "in" && <span className="nfl-live-dot" />}{label}</span><span className="nfl-kickoff">{row.state === "in" ? row.statusDetail || row.clock || "In progress" : kickoffLabel(row.kickoff)}</span></div>
    <div className="nfl-teams"><TeamRow row={row} side="away" /><TeamRow row={row} side="home" /></div>
    <div className="nfl-prediction">
      {row.pick ? <><div className="nfl-pick-line"><span><strong>{row.pick}</strong> to win <span className="nfl-prediction-stage">{predictionLabel(row)}</span></span><strong className="nfl-confidence">{confidence}%</strong></div><div className="nfl-probability-track" role="img" aria-label={`${confidence}% estimated chance of a ${row.pick} win`}><span style={{ width: `${confidence}%`, background: teamColor }} /></div></> : <span className="nfl-no-pick">No saved pick for this game</span>}
    </div>
    <div className="nfl-card-bottom"><span className={`nfl-result ${row.originalCorrect === true ? "is-correct" : row.originalCorrect === false ? "is-miss" : ""}`}>{row.originalCorrect === true ? "✓ Original pick won" : row.originalCorrect === false ? "× Original pick missed" : row.tied ? "Tie · excluded from record" : row.pick ? "Awaiting result" : "Outside the original pick slate"}</span><button type="button" className="nfl-details-link" onClick={() => onDetails(row)} aria-label={`Details for ${row.awayName} at ${row.homeName}`}>Details <span aria-hidden="true">↗</span></button></div>
  </article>;
}

function Detail({ row, onClose }) {
  if (!row) return null;
  const clockText = value => value ? value.slice(11, 16).replace(/^(\d{2}):(\d{2})$/, (_, h, m) => `${Number(h) % 12 || 12}:${m} ${Number(h) >= 12 ? "PM" : "AM"}`) : "Unavailable";
  return <div className="nfl-detail-body">
    <div className="nfl-detail-matchup"><img src={row.awayLogo} width="64" height="64" alt={`${row.awayName} logo`} /><span>at</span><img src={row.homeLogo} width="64" height="64" alt={`${row.homeName} logo`} /></div>
    <p className="nfl-detail-kickoff">{kickoffLabel(row.kickoff)} · {row.venue || "Venue unavailable"}</p>
    {row.pick && <section className="nfl-detail-section"><h3>Saved prediction</h3><div className="nfl-detail-pick"><strong>{row.pick} · {Math.round(row.pickProbability * 100)}%</strong><span>{predictionLabel(row)}</span></div><p>{row.forecastIssuedAt?.length === 10 ? `Issued ${row.forecastIssuedAt}` : `Issued ${new Date(row.forecastIssuedAt).toLocaleString("en-US", { timeZone: "America/New_York" })} ET`}</p><p>Estimated win probability, conditional on a decisive result.</p>{row.originalHomeProbability !== row.homeProbability && <p>Original pick: {row.originalPick} at {Math.round(Math.max(row.originalHomeProbability, 1 - row.originalHomeProbability) * 100)}%.</p>}</section>}
    <section className="nfl-detail-section"><h3>Quarterbacks in the saved forecast</h3><dl><div><dt>{row.awayCode}</dt><dd>{row.awayQb || "No saved projection"}</dd></div><div><dt>{row.homeCode}</dt><dd>{row.homeQb || "No saved projection"}</dd></div></dl></section>
    {row.totalProjection && <section className="nfl-detail-section" data-reviewed-rows><h3>Total points projection</h3><p><strong>{row.totalProjection.projected_total.toFixed(1)} combined points</strong> · Experimental</p><p>80% predictive range: {row.totalProjection.interval_80[0]}–{row.totalProjection.interval_80[1]} points. A separate scoring model; an over/under lean also requires the exact printed line.</p></section>}
    <section className="nfl-detail-section"><h3>Kickoff on each team’s home clock</h3><dl><div><dt>{row.awayCode}</dt><dd>{clockText(row.awayClockKickoff)}{row.awayTimeZoneShift ? ` · ${Math.abs(row.awayTimeZoneShift)}h ${row.awayTimeZoneShift > 0 ? "east" : "west"}` : row.awayTimeZoneShift === 0 ? " · Same time zone" : ""}</dd></div><div><dt>{row.homeCode}</dt><dd>{clockText(row.homeClockKickoff)}{row.homeTimeZoneShift ? ` · ${Math.abs(row.homeTimeZoneShift)}h ${row.homeTimeZoneShift > 0 ? "east" : "west"}` : row.homeTimeZoneShift === 0 ? " · Same time zone" : ""}</dd></div></dl><p>Experimental travel context. Arrival times and actual acclimation are unknown.</p></section>
    {row.shadowComparisons?.length > 0 && <section className="nfl-detail-section" data-reviewed-rows><h3>Model comparison</h3><p>Estimated chance of a {row.homeCode} win. Research models are tracked separately from the saved primary pick.</p><dl>{row.shadowComparisons.filter(item => ["efficiency_qb", "body_clock", "combined"].includes(item.model)).map(item => <div key={item.model}><dt>{{efficiency_qb: "Efficiency + QB", body_clock: "With body clock", combined: "All new metrics"}[item.model]}</dt><dd>{Math.round(item.homeProbability * 100)}% · Experimental</dd></div>)}{row.eloHomeProbability != null && <div><dt>Independent Elo</dt><dd>{Math.round(row.eloHomeProbability * 100)}%</dd></div>}{row.marketHomeProbability != null && <div><dt>Market benchmark</dt><dd>{Math.round(row.marketHomeProbability * 100)}% · Margin removed</dd></div>}</dl></section>}
    <div className="nfl-detail-actions"><Button className="nfl-detail-close" onClick={onClose}>Back to games</Button></div>
  </div>;
}

function BrochureCard({ rows, teams }) {
  const [expanded, setExpanded] = useState(false);
  return <><span id="nfl-weekly-totals" className="nfl-section-anchor" aria-hidden="true" /><DataComponent id="weekly-totals" queryId="brochure" title="Weekly over / under card" kind="custom" variant="plain" sourceRows={rows} displayRows={rows} description="Your three games and the exact printed totals. Results are tracked separately from winner picks." className="nfl-brochure-evidence">
    <Button className="nfl-total-toggle" aria-expanded={expanded} aria-controls="nfl-total-card-content" onClick={() => setExpanded(value => !value)}><span>{rows.length ? `${rows.length} games · Printed totals & results` : "Weekly totals"}</span><span>{expanded ? "Hide" : "View"} <span aria-hidden="true">{expanded ? "−" : "+"}</span></span></Button>
    <div id="nfl-total-card-content" className={`nfl-total-content ${expanded ? "is-expanded" : ""}`}>
    {rows.length ? <div className="nfl-brochure-grid">{rows.map(row => {
      const game = teams.find(game => game.eventId === row.eventId);
      return <article className="nfl-total-card" key={row.eventId} data-reviewed-rows>
        <div className="nfl-total-matchup"><span><img src={game?.awayLogo} alt={`${row.awayCode} logo`} width="30" height="30" />{row.awayCode}</span><small>at</small><span><img src={game?.homeLogo} alt={`${row.homeCode} logo`} width="30" height="30" />{row.homeCode}</span></div>
        <div className="nfl-total-line"><span>Printed total</span><strong>{row.line}</strong></div>
        {row.analysis ? <><div className="nfl-total-lean"><strong>{row.analysis.lean === "Even" ? "No lean" : row.analysis.lean} · {row.line}</strong><span>{Math.round(Math.max(row.analysis.over_probability,row.analysis.under_probability)*100)}% · Experimental</span></div><p>Projected total: {row.projection.projected_total.toFixed(1)} · 80% range {row.projection.interval_80[0]}–{row.projection.interval_80[1]}</p>{row.analysis.push_probability > 0 && <p>Push: {Math.round(row.analysis.push_probability*100)}%</p>}</> : <p className="nfl-total-unavailable">No pregame forecast recorded</p>}
        <div className="nfl-total-result">{row.actualOutcome ? <><strong>{row.actualOutcome} · {row.actualTotal} points</strong><span>{row.correct === true ? "Model lean correct" : row.correct === false ? "Model lean missed" : row.actualOutcome === "Push" ? "Push · separate from wins/losses" : row.analysis?.lean === "Even" ? "50/50 · excluded from pick record" : "Historical result"}</span></> : <span>Awaiting final score</span>}</div>
      </article>;
    })}</div> : <p className="nfl-total-empty">Send your three matchups and their printed totals each week to add the next card.</p>}
    <p className="nfl-total-note">New totals predictions use a separate scoring model. Games already underway never receive a new pick. Contest settlement follows the card’s own rules.</p>
    </div>
  </DataComponent></>;
}

export function DashboardContent() {
  const { snapshot, queries, visible } = useDataApp();
  const [status, setStatus] = useState("all");
  const [slate, setSlate] = useState("all");
  const [sort, setSort] = useState("live");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [tick, setTick] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setTick(Date.now()), 15000); return () => clearInterval(timer); }, []);
  const all = queries.matchups?.rows || [];
  const brochure = queries.brochure?.rows || [];
  const filtered = useMemo(() => orderedGames(filterGames(all, { status, slate, search }), sort), [all, status, slate, search, sort]);
  const summary = gameSummary(filtered);
  const selectedRow = selected ? all.find(row => row.eventId === selected.eventId) || selected : null;
  const age = sourceAgeLabel(queries.matchups?.source?.executedAt || snapshot.generatedAt, tick);
  const stale = age.stale || snapshot.nflFeed?.status === "unavailable";
  return <div className="nfl-dashboard">
    <div className="nfl-week-toolbar"><div className="nfl-week-label"><span className="nfl-season">{snapshot.period?.season} NFL season</span><strong>Week {snapshot.period?.week}</strong></div><div className="nfl-feed-controls"><span className={`nfl-feed-label ${stale ? "is-stale" : ""}`} role="status"><span className="nfl-feed-dot" />{stale ? "Last update" : snapshot.nflFeed?.status === "connected" ? "Scores updated" : "Snapshot"} {age.text}</span><Button className="nfl-refresh-button" onClick={() => window.dispatchEvent(new Event("nfl:refresh-scores"))} aria-label="Refresh scores"><Icon name="refresh" />Refresh scores</Button></div></div>
    {snapshot.nflFeed?.error && <div className="nfl-feed-warning" role="status">Live updates are temporarily unavailable. Scores below retain their last successful update.</div>}
    <nav className="nfl-mobile-nav" aria-label="Dashboard sections"><a href="#nfl-matchups">Games · {all.length}</a>{queries.brochure && visible("weekly-totals") && <a href="#nfl-weekly-totals">Over / under · {brochure.length}</a>}</nav>
    {visible("week-overview") && <DataComponent id="week-overview" queryId="matchups" title="This week" kind="custom" variant="plain" sourceRows={filtered} displayRows={filtered} className="nfl-overview-evidence"><div className="nfl-overview" data-reviewed-rows><div><span>Matchups shown</span><strong>{summary.games}</strong></div><div><span>Live now</span><strong className={summary.live ? "nfl-live-count" : ""}>{summary.live}</strong></div><div><span>Still to come</span><strong>{summary.upcoming}</strong></div><div><span>Original picks record</span><strong>{summary.decided ? `${summary.wins}–${summary.losses}` : "—"}</strong><small>{summary.decided ? `${summary.decided} completed ${summary.decided === 1 ? "pick" : "picks"}` : "No completed picks in this view"}</small></div></div></DataComponent>}
    {queries.brochure && visible("weekly-totals") && <BrochureCard rows={brochure} teams={all} />}
    <span id="nfl-matchups" className="nfl-section-anchor" aria-hidden="true" />
    <SortableRegion id="nfl:matchups" variant="freeform" authoredRevision={1} className="nfl-matchup-region">
      <SortableItem id="weekly-games" label="Weekly matchups" kind="custom"><DataComponent id="weekly-games" queryId="matchups" title="Matchups" kind="custom" variant="plain" sourceRows={filtered} displayRows={filtered} description="Saved pregame predictions with current scores. Later revisions never change the original picks record." className="nfl-grid-evidence" headerControls={<div className="nfl-filter-controls"><SegmentedControl className="nfl-status-control" size="default" fullWidth ariaLabel="Game status" value={status} onChange={setStatus} options={[{ value: "all", ariaLabel: "All games", label: <><span className="nfl-filter-full">All games</span><span className="nfl-filter-short">All</span></> }, { value: "in", label: "Live" }, { value: "pre", ariaLabel: "Upcoming", label: <><span className="nfl-filter-full">Upcoming</span><span className="nfl-filter-short">Next</span></> }, { value: "post", label: "Final" }]} /></div>}>
        <div className="nfl-secondary-controls"><label className="nfl-search"><span className="nfl-visually-hidden">Search teams</span><input type="search" placeholder="Find a team or matchup…" value={search} onChange={event => setSearch(event.target.value)} /></label><div className="nfl-select-controls"><Dropdown label="Slate" showLabel triggerClassName="filter-trigger nfl-select-trigger" value={slate} onChange={setSlate} choices={["all", "sunmon"]} choiceLabels={{ all: "Full week", sunmon: "Sunday + Monday" }} /><Dropdown label="Sort" showLabel triggerClassName="filter-trigger nfl-select-trigger" value={sort} onChange={setSort} choices={["live", "kickoff", "confidence"]} choiceLabels={{ live: "Live first", kickoff: "Kickoff time", confidence: "Pick confidence" }} /></div></div>
        {filtered.length ? <div className="nfl-game-grid">{filtered.map(row => <GameCard key={row.eventId} row={row} onDetails={setSelected} />)}</div> : <div className="nfl-empty"><strong>No games match this view.</strong><p>Try another status, slate or team name.</p><Button onClick={() => { setStatus("all"); setSlate("all"); setSearch(""); }}>Show all games</Button></div>}
      </DataComponent></SortableItem>
    </SortableRegion>
    <footer className="nfl-footer"><span>Team logos: NFL.com · Scores: ESPN</span><span>Preliminary picks require a final lineup check.</span></footer>
    <Dialog className="nfl-game-dialog" open={Boolean(selectedRow)} onClose={() => setSelected(null)} title={selectedRow ? `${selectedRow.awayName} at ${selectedRow.homeName}` : "Game details"}><Detail row={selectedRow} onClose={() => setSelected(null)} /></Dialog>
  </div>;
}
