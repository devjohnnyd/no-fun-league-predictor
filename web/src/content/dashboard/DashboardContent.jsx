import React, { useEffect, useMemo, useState } from "react";
import { Button, DataComponent, Dialog, Dropdown, Icon, SegmentedControl, SortableItem, SortableRegion, useDataApp } from "../../data-app-public.jsx";
import { filterGames, gameSummary, inputFreshness, kickoffLabel, orderedGames, predictionLabel, sourceAgeLabel, spreadLabel, totalRecord, weeklyTossUp } from "./football.mjs";
import { useAnalysisRefresh } from "./use-analysis-refresh.js";
import { NflViews, PerformanceContent } from "../performance/PerformanceContent.jsx";

function MarketTotal({ total, state }) {
  if (!total) return <div className="nfl-market-total"><span>Over / under</span><p>Refresh to load available market totals.</p></div>;
  const analysis = total.analysis;
  return <div className="nfl-market-total" data-reviewed-rows>
    <div className="nfl-market-heading"><strong>Over / under</strong><strong>{total.latestLine ?? "Line unavailable"}</strong></div>
    {total.latestLine != null && <p>{total.book} · {total.quoteStatus}<br />First observed {total.firstObservedLine} · Move {total.movement > 0 ? "+" : ""}{total.movement}</p>}
    {total.projection ? <p>Projected {total.projection.projected_total.toFixed(1)} · 80% range {total.projection.interval_80.join("–")}</p> : <p>{state === "post" || state === "in" ? "No saved pregame projection" : "Projection pending fresh pregame inputs"}</p>}
    {analysis && <p><strong>Latest analysis: {analysis.lean === "Even" ? "No lean" : analysis.lean} {total.latestLine}</strong> · {Math.round(Math.max(analysis.over_probability, analysis.under_probability) * 100)}%</p>}
    {total.originalPick ? <p className={total.correct === true ? "nfl-total-won" : total.correct === false ? "nfl-total-lost" : ""}>Tracked pick: {total.originalPick.lean} {total.originalLine} · {total.correct === true ? "Won" : total.correct === false ? "Lost" : total.actualOutcome === "Push" ? "Push" : "Pending"}</p> : <p>No pregame market pick recorded</p>}
    {total.observedAt && <small>Line seen {new Date(total.observedAt).toLocaleString("en-US", {timeZone:"America/New_York", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"})} ET</small>}
  </div>;
}

function MarketSpread({ row }) {
  const spread = row.marketSpread;
  const analysis = spread?.analysis;
  const margin = spread?.projection?.projected_home_margin;
  const status = spread?.correct === true ? "Won" : spread?.correct === false ? "Lost" : spread?.actualOutcome === "Push" ? "Push" : "Pending";
  return <div className="nfl-market-total" data-reviewed-rows>
    <div className="nfl-market-heading"><strong>Point spread</strong><strong>{spreadLabel(row, spread?.latestLine)}</strong></div>
    {spread?.latestLine != null && <p>{spread.book} · {spread.quoteStatus}{spread.movement !== 0 && <> · First seen {spreadLabel(row, spread.firstObservedLine)}</>}</p>}
    {analysis && <p><strong>{analysis.lean === "Even" ? "No spread lean" : `Cover pick: ${spreadLabel(row, spread.latestLine, analysis.lean)}`}</strong>{analysis.lean !== "Even" && ` · ${Math.round(Math.max(analysis.home_cover_probability, analysis.away_cover_probability) * 100)}%`}</p>}
    {margin != null && <p>Projected margin: {Math.abs(margin) < .05 ? "Tied" : `${margin > 0 ? row.homeCode : row.awayCode} by ${Math.abs(margin).toFixed(1)}`} · Experimental</p>}
    {spread?.originalPick ? <p className={status === "Won" ? "nfl-total-won" : status === "Lost" ? "nfl-total-lost" : ""}>Tracked pick: {spreadLabel(row, spread.originalLine, spread.originalPick.lean)} · {status}</p> :
      <p>{row.state === "pre" ? margin == null ? "Spread pick pending fresh pregame inputs" : "Awaiting a directional pick at a current line" : "No saved pregame spread pick"}</p>}
  </div>;
}

function TossUp({ spotlight, onDetails }) {
  if (!spotlight) return null;
  const { row, forecastCount, quoteCount } = spotlight;
  const home = Math.round(row.homeProbability * 100);
  const away = 100 - home;
  return <DataComponent id="weekly-toss-up" queryId="matchups" title="Toss-up of the week" showHeading={false} kind="custom" variant="plain" sourceRows={[row]} displayRows={[row]} className="nfl-toss-up-evidence">
    <section className="nfl-toss-up" aria-labelledby="nfl-toss-up-title" data-reviewed-rows>
      <div className="nfl-toss-up-copy">
        <h2 id="nfl-toss-up-title">Toss-up of the week</h2>
        <p>{kickoffLabel(row.kickoff)}{row.state === "post" ? " · Final" : row.state === "in" ? " · Live" : ""}</p>
        <button type="button" className="nfl-details-link" onClick={() => onDetails(row)}>Matchup details <span aria-hidden="true">↗</span></button>
      </div>
      <div className="nfl-toss-up-data">
        <div className="nfl-toss-up-teams">
          <span><img src={row.awayLogo} alt="" width="44" height="44" />{row.awayCode}{forecastCount > 0 && <strong>{away}%</strong>}</span>
          <small>at</small>
          <span>{forecastCount > 0 && <strong>{home}%</strong>}{row.homeCode}<img src={row.homeLogo} alt="" width="44" height="44" /></span>
        </div>
        {forecastCount > 0 ? <>
          <div className="nfl-toss-up-track" role="img" aria-label={`${row.awayName} ${away}% and ${row.homeName} ${home}% estimated win probability`}><span style={{ width: `${away}%` }} /></div>
          <p>{row.homeProbability === .5 ? "50/50 on the model" : `Model leans ${row.pick}`} · Closest of {forecastCount} saved winner {forecastCount === 1 ? "pick" : "picks"}</p>
        </> : <p>{spreadLabel(row, row.marketSpread.latestLine)} · Tightest of {quoteCount} quoted lines · Model pick pending</p>}
      </div>
    </section>
  </DataComponent>;
}

function TeamRow({ row, side }) {
  const opponent = side === "home" ? "away" : "home";
  const winner = row.state === "post" && row[side + "Score"] > row[opponent + "Score"];
  return <div className={`nfl-team ${winner ? "is-winner" : ""}`}>
    <span className="nfl-logo-well"><img src={row[side + "Logo"]} alt={`${row[side + "Name"]} logo`} width="46" height="46" loading="lazy" /></span>
    <div className="nfl-team-identity"><span className="nfl-team-name">{row[side + "Name"]}</span><span className="nfl-team-code">{row[side + "Code"]}{side === "home" ? " · Home" : " · Away"}</span></div>
    <span className="nfl-score" aria-label={row[side + "Score"] == null ? "Not started" : `${row[side + "Score"]} points`}>{row[side + "Score"] ?? "—"}</span>
  </div>;
}

const LOCK_PASSWORD_KEY = "nfl-lock-password";
const etTime = value => new Date(value).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " ET";

function readStoredPassword() {
  try { return window.localStorage.getItem(LOCK_PASSWORD_KEY) || ""; } catch { return ""; }
}

function storePassword(value) {
  try { value ? window.localStorage.setItem(LOCK_PASSWORD_KEY, value) : window.localStorage.removeItem(LOCK_PASSWORD_KEY); } catch { /* Locking still works; the password is just asked again. */ }
}

function QbLine({ row }) {
  const locked = row.lock?.snapshot?.qbs;
  const atPick = locked || { home: { name: row.homeQb }, away: { name: row.awayQb } };
  if (!atPick.home?.name && !atPick.away?.name) return null;
  const now = row.currentQbs;
  const changed = ["away", "home"].filter(side => now?.[side]?.name && atPick[side]?.name && now[side].name !== atPick[side].name);
  return <div className="nfl-qb-line" data-reviewed-rows>
    <span>{locked ? "Starting QBs when locked" : "Starting QBs in this pick"}</span>
    <strong>{row.awayCode} {atPick.away?.name || "Unknown"} · {row.homeCode} {atPick.home?.name || "Unknown"}</strong>
    {changed.map(side => <small key={side} className="nfl-qb-alert">QB change: {row[side + "Code"]} now projects {now[side].name}</small>)}
  </div>;
}

function LockStatus({ row }) {
  if (row.lock) {
    const major = row.lock.changes.filter(item => item.severity === "major").length;
    const count = row.lock.changes.length;
    return <div className="nfl-lock-status" data-reviewed-rows>
      <span className="nfl-lock-badge">Locked {etTime(row.lock.lockedAt)}</span>
      <span className={`nfl-lock-changes ${major ? "is-major" : ""}`}>{count ? `${count} ${count === 1 ? "change" : "changes"} since lock${major ? ` · ${major} major` : ""}` : "No changes since lock"}</span>
    </div>;
  }
  return null;
}

function marketLabel(row, market, kind) {
  if (!market || market.line == null) return "Unavailable";
  const directional = market.lean && market.lean !== "Even";
  if (kind === "spread") return directional ? `${spreadLabel(row, market.line, market.lean)} · ${Math.round(market.probability * 100)}%` : `${spreadLabel(row, market.line)} · No lean`;
  return directional ? `${market.lean} ${market.line} · ${Math.round(market.probability * 100)}%` : `${market.line} · No lean`;
}

function weatherLabel(weather) {
  if (!weather) return "Unavailable";
  if (weather.outdoor === false) return "Indoors";
  const parts = [weather.temperature_f != null && `${Math.round(weather.temperature_f)}°F`, weather.wind_mph != null && `wind ${Math.round(weather.wind_mph)} mph`,
    weather.precip_probability != null && `${Math.round(weather.precip_probability * 100)}% rain`].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Unavailable";
}

function injuryLabel(list) {
  const listed = (list || []).filter(item => ["Out", "Doubtful", "Questionable"].includes(item.status));
  return listed.length ? listed.map(item => `${item.name} (${item.position}) ${item.status}`).join(", ") : "None listed";
}

function currentMarket(market, probabilities) {
  if (!market) return null;
  const analysis = market.analysis;
  return { line: market.latestLine, lean: analysis?.lean, probability: analysis ? Math.max(...probabilities.map(key => analysis[key])) : null };
}

function LockedBet({ row }) {
  const lock = row.lock;
  if (!lock) return null;
  const then = lock.snapshot;
  const probability = team => Math.round((team === row.homeCode ? row.homeProbability : 1 - row.homeProbability) * 100);
  const lines = [
    ["Winner pick", `${then.pick} · ${Math.round(then.pickProbability * 100)}%`, row.pick ? `${row.pick} · ${probability(row.pick)}%` : "No saved pick"],
    [`${row.awayCode} QB`, then.qbs.away?.name || "Unknown", row.currentQbs?.away?.name || "Unknown"],
    [`${row.homeCode} QB`, then.qbs.home?.name || "Unknown", row.currentQbs?.home?.name || "Unknown"],
    ["Spread", marketLabel(row, then.spread, "spread"), marketLabel(row, currentMarket(row.marketSpread, ["home_cover_probability", "away_cover_probability"]), "spread")],
    ["Total", marketLabel(row, then.total, "total"), marketLabel(row, currentMarket(row.marketTotal, ["over_probability", "under_probability"]), "total")],
    ["Weather", weatherLabel(then.weather), weatherLabel(row.weather)],
    [`${row.awayCode} injuries`, injuryLabel(then.injuries.away), injuryLabel(row.awayInjuries)],
    [`${row.homeCode} injuries`, injuryLabel(then.injuries.home), injuryLabel(row.homeInjuries)]
  ];
  const ordered = [...lock.changes].sort((a, b) => (a.severity === "major" ? 0 : 1) - (b.severity === "major" ? 0 : 1));
  const graded = lock.result;
  return <section className="nfl-detail-section nfl-locked-bet" data-reviewed-rows>
    <h3>Locked bet</h3>
    <p>Locked {etTime(lock.lockedAt)} · Forecast issued {then.forecastIssuedAt?.length === 10 ? then.forecastIssuedAt : etTime(then.forecastIssuedAt)}{then.qbs.source === "Latest input check" ? ` · QBs from the ${etTime(then.qbs.checkedAt)} input check` : ""}</p>
    {graded && <div className="nfl-lock-result">
      <span className={`is-${graded.winner.toLowerCase()}`}>Winner: {graded.winner}</span>
      {graded.spread && <span className={`is-${graded.spread.toLowerCase()}`}>Spread: {graded.spread}</span>}
      {graded.total && <span className={`is-${graded.total.toLowerCase()}`}>Total: {graded.total}</span>}
    </div>}
    {graded?.latestPick && <p className="nfl-lock-hindsight">Hindsight: the latest pregame pick, {graded.latestPick.pick}, {graded.latestPick.outcome === "Won" ? "would have won" : "would also have lost"}.</p>}
    <div className="nfl-history-scroll" tabIndex={0} role="region" aria-label="Locked bet compared with now">
      <table className="nfl-lock-table"><thead><tr><th>Input</th><th>At lock</th><th>{row.state === "pre" ? "Now" : "Last before kickoff"}</th></tr></thead>
        <tbody>{lines.map(([label, before, after]) => <tr key={label} className={before !== after ? "is-changed" : ""}><th scope="row">{label}</th><td>{before}</td><td>{after}</td></tr>)}</tbody>
      </table>
    </div>
    <h4>What changed after locking</h4>
    {ordered.length ? <ul className="nfl-lock-change-list">{ordered.map(item => <li key={`${item.kind}:${item.label}`} className={item.severity === "major" ? "is-major" : ""}><strong>{item.label}</strong>: {item.before} → {item.after}</li>)}</ul> : <p>Nothing material changed after this bet was locked.</p>}
    <p>The snapshot is saved on the server and never rewritten. Major changes could flip a bet: a different starting QB, a pick or lean that flipped, or a player newly ruled out.</p>
  </section>;
}

function LockDialog({ rows, week, onClose }) {
  const [password, setPassword] = useState(readStoredPassword);
  const [chosen, setChosen] = useState(() => new Set(rows.map(row => row.eventId)));
  const [state, setState] = useState({ busy: false, error: "", locked: 0 });
  const toggle = eventId => setChosen(previous => { const next = new Set(previous); next.has(eventId) ? next.delete(eventId) : next.add(eventId); return next; });
  const submit = async event => {
    event.preventDefault();
    setState({ busy: true, error: "", locked: 0 });
    let locked = 0;
    try {
      for (const row of rows.filter(item => chosen.has(item.eventId))) {
        const response = await fetch(new URL("./api/lock", window.location.href).href, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ week, eventId: row.eventId, password }) });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 403) storePassword("");
          throw new Error(`${row.awayCode} at ${row.homeCode}: ${body.error || "Unable to lock this bet."}`);
        }
        storePassword(password);
        locked += 1;
        setState(previous => ({ ...previous, locked }));
      }
      window.dispatchEvent(new Event("nfl:refresh-scores"));
      onClose();
    } catch (error) {
      if (locked) window.dispatchEvent(new Event("nfl:refresh-scores"));
      setState({ busy: false, error: locked ? `${error.message} ${locked} earlier ${locked === 1 ? "bet was" : "bets were"} locked.` : error.message, locked });
    }
  };
  const count = rows.filter(row => chosen.has(row.eventId)).length;
  return <form className="nfl-lock-form" onSubmit={submit}>
    <p>Each locked game records the pick, both starting QBs, injuries, weather and the current spread and total as they are now. Locks cannot be edited or undone.</p>
    <ul className="nfl-lock-picks">{rows.map(row => <li key={row.eventId}><label>
      <input type="checkbox" checked={chosen.has(row.eventId)} onChange={() => toggle(row.eventId)} disabled={state.busy} />
      <span><strong>{row.awayCode} at {row.homeCode}</strong> · {row.pick} {Math.round(row.pickProbability * 100)}%<small>{row.currentQbs?.away?.name || "Unknown"} vs {row.currentQbs?.home?.name || "Unknown"} · {kickoffLabel(row.kickoff)}</small></span>
    </label></li>)}</ul>
    <label className="nfl-lock-password"><span>Lock password</span><input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
    {state.error && <p className="nfl-lock-error" role="alert">{state.error}</p>}
    <div className="nfl-detail-actions"><Button onClick={onClose}>Cancel</Button><Button type="submit" className="nfl-lock-button" disabled={state.busy || !password || !count}>{state.busy ? `Locking ${state.locked + 1} of ${count}…` : `Lock in ${count} ${count === 1 ? "bet" : "bets"}`}</Button></div>
  </form>;
}

function GameCard({ row, onDetails }) {
  const label = row.state === "in" ? "Live" : row.state === "post" ? "Final" : row.state === "pre" ? "Upcoming" : row.statusDetail || "Status unavailable";
  const confidence = row.pickProbability == null ? null : Math.round(row.pickProbability * 100);
  const color = row.pick === row.homeCode ? row.homeColor : row.awayColor;
  const teamColor = /^[0-9a-f]{6}$/i.test(color || "") ? `#${color}` : "var(--accent)";
  // Results grade the original pick, so name it when a later revision shows a different team.
  const originalNote = row.originalPick && row.originalPick !== row.pick ? ` (${row.originalPick})` : "";
  return <article className={`nfl-game ${row.state === "in" ? "is-live" : ""}`} data-testid="game-card" data-event-id={row.eventId} data-reviewed-rows>
    <div className="nfl-game-top"><span className={`nfl-status state-${row.state}`}>{row.state === "in" && <span className="nfl-live-dot" />}{label}</span><span className="nfl-kickoff">{row.state === "in" ? row.statusDetail || row.clock || "In progress" : kickoffLabel(row.kickoff)}</span></div>
    <div className="nfl-teams"><TeamRow row={row} side="away" /><TeamRow row={row} side="home" /></div>
    <div className="nfl-prediction">
      {row.pick ? <><div className="nfl-pick-line"><span><strong>{row.pick}</strong> to win <span className="nfl-prediction-stage">{predictionLabel(row)}</span></span><strong className="nfl-confidence">{confidence}%</strong></div><div className="nfl-probability-track" role="img" aria-label={`${confidence}% estimated chance of a ${row.pick} win`}><span style={{ width: `${confidence}%`, background: teamColor }} /></div></> : <span className="nfl-no-pick">No saved pick for this game</span>}
    </div>
    <QbLine row={row} />
    <MarketTotal total={row.marketTotal} state={row.state} />
    <MarketSpread row={row} />
    <LockStatus row={row} />
    <div className="nfl-card-bottom"><span className={`nfl-result ${row.originalCorrect === true ? "is-correct" : row.originalCorrect === false ? "is-miss" : ""}`}>{row.originalCorrect === true ? `✓ Original winner pick${originalNote} won` : row.originalCorrect === false ? `× Original winner pick${originalNote} missed` : row.tied ? "Tie · excluded from record" : row.pick ? "Awaiting winner result" : "No saved winner pick"}</span><button type="button" className="nfl-details-link" onClick={() => onDetails(row)} aria-label={`Details for ${row.awayName} at ${row.homeName}`}>Details <span aria-hidden="true">↗</span></button></div>
  </article>;
}

function BackgroundLines({ collection, week }) {
  if (!collection) return null;
  const current = collection.weeks?.find(item => item.week === week);
  const time = value => new Date(value).toLocaleString("en-US", {timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) + " ET";
  return <details className="nfl-automation"><summary>Background lines · {collection.enabled ? "On" : "Off"}{current?.state === "failed" ? " · Retry pending" : ""}</summary>
    <p>{collection.cadence}</p>
    {current ? <><p>Week {week}: {current.message || "Checking available quotes…"}</p>
      {current.lastSuccessAt && <p>Last successful source check: {time(current.lastSuccessAt)}<br />Last pregame quote captured: {current.lastQuoteAt ? time(current.lastQuoteAt) : "None yet"}</p>}
      {current.nextCheckAt && <p>Next check due: {time(current.nextCheckAt)}</p>}
    </> : <p>This week is outside the current collection window or awaiting its first check. Upcoming games enter collection eight days before kickoff.</p>}
    {collection.error && <p role="status">{collection.error}</p>}
    <p>{collection.provider}. Checks capture totals and spreads. The coverage above counts games with total quotes. Line refreshes reuse saved pregame projections.</p>
  </details>;
}

function InputStatus({ row, latest, now }) {
  const sources = latest?.sources || row.forecastSources || {};
  const historical = row.state === "post" || row.state === "in";
  const asOf = historical ? Date.parse(row.forecastIssuedAt) : now;
  return <section className="nfl-detail-section" data-reviewed-rows><h3>{historical ? "Saved input receipts" : "Pregame input freshness"}</h3>
    {latest?.check && <p>{latest.check.stage === "final" ? "Final" : "Preliminary"} check: {latest.check.ready ? "Passed" : "Blocked"} · {new Date(latest.check.checked_at).toLocaleString("en-US", {timeZone:"America/New_York"})} ET</p>}
    <dl>{Object.entries({stats:"Team & QB statistics", injuries:"Injury reports", depth:"Projected quarterbacks", weather:"Kickoff weather", staff:"Coaching staff", inactives:"Official inactive lists"}).map(([kind,label]) => {
      const source = sources[kind];
      const age = inputFreshness(source, kind, asOf, latest?.check?.stage === "final");
      return <div key={kind}><dt>{label}</dt><dd className={age.stale ? "nfl-input-stale" : ""}>{source?.url?.startsWith("https://") ? <a href={source.url} target="_blank" rel="noreferrer">{age.label}</a> : age.label}{source?.retrieved_at && <small>{new Date(source.retrieved_at).toLocaleString("en-US", {timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})} ET</small>}</dd></div>;
    })}</dl>
    {latest?.check?.reasons?.length > 0 && <ul>{latest.check.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
    <p>{historical ? "Ages are measured when the saved forecast was issued." : "Fresh reports support preliminary picks. Final picks also require verified official inactive lists for both teams; missing evidence blocks release."}</p>
  </section>;
}

function SpreadHistory({ row }) {
  const history = row.marketSpread?.history || [];
  return <section className="nfl-detail-section" data-reviewed-rows>
    <h3>Point spread and line history</h3>
    <MarketSpread row={row} />
    {history.length > 0 && <div className="nfl-history-scroll" tabIndex={0} role="region" aria-label="Spread line observations">
      <table><thead><tr><th>Observed (ET)</th><th>Provider</th><th>Home spread</th><th>Cover pick then</th></tr></thead>
        <tbody>{history.map(item => <tr key={`${item.book_id}:${item.observed_at}`}>
          <td>{new Date(item.observed_at).toLocaleString("en-US", {timeZone:"America/New_York", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"})}</td>
          <td>{item.book}</td><td>{spreadLabel(row, item.line)}</td>
          <td>{!item.analysis ? "No forecast" : item.analysis.lean === "Even" ? "No lean" : spreadLabel(row, item.line, item.analysis.lean)}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    <p>A cover means the selected team’s score plus its spread beats its opponent’s score. Equal adjusted scores are a push. Results use the first saved directional pick and its exact line.</p>
  </section>;
}

function Detail({ row, onClose, latest, now }) {
  if (!row) return null;
  const clockText = value => value ? value.slice(11, 16).replace(/^(\d{2}):(\d{2})$/, (_, h, m) => `${Number(h) % 12 || 12}:${m} ${Number(h) >= 12 ? "PM" : "AM"}`) : "Unavailable";
  return <div className="nfl-detail-body">
    <div className="nfl-detail-matchup"><img src={row.awayLogo} width="64" height="64" alt={`${row.awayName} logo`} /><span>at</span><img src={row.homeLogo} width="64" height="64" alt={`${row.homeName} logo`} /></div>
    <p className="nfl-detail-kickoff">{kickoffLabel(row.kickoff)} · {row.venue || "Venue unavailable"}</p>
    <LockedBet row={row} />
    {row.pick && <section className="nfl-detail-section"><h3>Saved prediction</h3><div className="nfl-detail-pick"><strong>{row.pick} · {Math.round(row.pickProbability * 100)}%</strong><span>{predictionLabel(row)}</span></div><p>{row.forecastIssuedAt?.length === 10 ? `Issued ${row.forecastIssuedAt}` : `Issued ${new Date(row.forecastIssuedAt).toLocaleString("en-US", { timeZone: "America/New_York" })} ET`}</p><p>Estimated win probability, conditional on a decisive result.</p>{row.originalHomeProbability !== row.homeProbability && <p>Original pick: {row.originalPick} at {Math.round(Math.max(row.originalHomeProbability, 1 - row.originalHomeProbability) * 100)}%.</p>}</section>}
    <section className="nfl-detail-section"><h3>Quarterbacks in the saved forecast</h3><dl><div><dt>{row.awayCode}</dt><dd>{row.awayQb || "No saved projection"}{row.awayQbStatus && ` · ${row.awayQbStatus}`}</dd></div><div><dt>{row.homeCode}</dt><dd>{row.homeQb || "No saved projection"}{row.homeQbStatus && ` · ${row.homeQbStatus}`}</dd></div></dl>{row.currentQbs?.source === "Latest input check" && <p>Latest input check ({etTime(row.currentQbs.checkedAt)}): {row.awayCode} {row.currentQbs.away?.name || "Unknown"} · {row.homeCode} {row.currentQbs.home?.name || "Unknown"}</p>}</section>
    <InputStatus row={row} latest={latest} now={now} />
    {row.totalProjection && <section className="nfl-detail-section" data-reviewed-rows><h3>Total points projection</h3><p><strong>{row.totalProjection.projected_total.toFixed(1)} combined points</strong> · Experimental</p><p>80% predictive range: {row.totalProjection.interval_80[0]}–{row.totalProjection.interval_80[1]} points. A separate scoring model; an over/under lean also requires the exact printed line.</p></section>}
    <section className="nfl-detail-section"><h3>Kickoff on each team’s home clock</h3><dl><div><dt>{row.awayCode}</dt><dd>{clockText(row.awayClockKickoff)}{row.awayTimeZoneShift ? ` · ${Math.abs(row.awayTimeZoneShift)}h ${row.awayTimeZoneShift > 0 ? "east" : "west"}` : row.awayTimeZoneShift === 0 ? " · Same time zone" : ""}</dd></div><div><dt>{row.homeCode}</dt><dd>{clockText(row.homeClockKickoff)}{row.homeTimeZoneShift ? ` · ${Math.abs(row.homeTimeZoneShift)}h ${row.homeTimeZoneShift > 0 ? "east" : "west"}` : row.homeTimeZoneShift === 0 ? " · Same time zone" : ""}</dd></div></dl><p>Experimental travel context. Arrival times and actual acclimation are unknown.</p></section>
    {row.shadowComparisons?.length > 0 && <section className="nfl-detail-section" data-reviewed-rows><h3>Model comparison</h3><p>Estimated chance of a {row.homeCode} win. Research models are tracked separately from the saved primary pick.</p><dl>{row.shadowComparisons.filter(item => ["efficiency_qb", "body_clock", "combined"].includes(item.model)).map(item => <div key={item.model}><dt>{{efficiency_qb: "Efficiency + QB", body_clock: "With body clock", combined: "All new metrics"}[item.model]}</dt><dd>{Math.round(item.homeProbability * 100)}% · Experimental</dd></div>)}{row.eloHomeProbability != null && <div><dt>Independent Elo</dt><dd>{Math.round(row.eloHomeProbability * 100)}%</dd></div>}{row.marketHomeProbability != null && <div><dt>Market benchmark</dt><dd>{Math.round(row.marketHomeProbability * 100)}% · Margin removed</dd></div>}</dl></section>}
    <section className="nfl-detail-section"><h3>Market total and line history</h3><MarketTotal total={row.marketTotal} />{row.marketTotal?.forecastIssuedAt && <p>Projection issued {new Date(row.marketTotal.forecastIssuedAt).toLocaleString("en-US", {timeZone:"America/New_York"})} ET. Refreshing a line can change its lean without rebuilding these model inputs.</p>}{row.marketTotal?.history?.length > 0 && <div className="nfl-history-scroll" tabIndex={0} role="region" aria-label="Total line observations"><table><thead><tr><th>Observed (ET)</th><th>Provider</th><th>Line</th><th>Analysis then</th></tr></thead><tbody>{row.marketTotal.history.map(item => <tr key={`${item.book_id}:${item.observed_at}`}><td>{new Date(item.observed_at).toLocaleString("en-US", {timeZone:"America/New_York", month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})}</td><td>{item.book}</td><td>{item.line}</td><td>{item.analysis?.lean || "No forecast"}</td></tr>)}</tbody></table></div>}<p>First observed is the first quote captured by this tracker, rather than the market opening line. Quotes may be delayed; provider update time is unknown. Printed brochure totals remain fixed and separate.</p></section>
    {row.marketTotal?.historyObservationCount > row.marketTotal?.history?.length && <p className="nfl-history-note">Showing {row.marketTotal.history.length} line/analysis changes and latest provider checks from {row.marketTotal.historyObservationCount} captured observations. Every timestamped observation remains saved on the server.</p>}
    <SpreadHistory row={row} />
    <div className="nfl-detail-actions"><Button className="nfl-detail-close" onClick={onClose}>Back to games</Button></div>
  </div>;
}

function TotalRecord({ label, record }) {
  return <div><span>{label}</span><strong>{record.selections ? `${record.wins}–${record.losses}` : "—"}</strong><small>{record.pending} pending · {record.pushes} pushes{record.abstentions ? ` · ${record.abstentions} no lean` : ""}{record.unavailable ? ` · ${record.unavailable} without a pick` : ""}</small></div>;
}

function BrochureCard({ rows, teams, onDetails }) {
  const [expanded, setExpanded] = useState(false);
  return <><span id="nfl-weekly-totals" className="nfl-section-anchor" aria-hidden="true" /><DataComponent id="weekly-totals" queryId="brochure" title="Your printed card" kind="custom" variant="plain" sourceRows={rows} displayRows={rows} description="Fixed brochure selections, tracked separately from the market totals on every game below." className="nfl-brochure-evidence">
    <div className="nfl-total-records" data-reviewed-rows><TotalRecord label="Your totals record" record={totalRecord(rows, "user")} /><TotalRecord label="Model totals record" record={totalRecord(rows)} /></div>
    <Button className="nfl-total-toggle" aria-expanded={expanded} aria-controls="nfl-total-card-content" onClick={() => setExpanded(value => !value)}><span>{rows.length ? `${rows.length} games · Printed totals & results` : "Weekly totals"}</span><span>{expanded ? "Hide" : "View"} <span aria-hidden="true">{expanded ? "−" : "+"}</span></span></Button>
    <div id="nfl-total-card-content" className={`nfl-total-content ${expanded ? "is-expanded" : ""}`}>
    {rows.length ? <div className="nfl-brochure-grid">{rows.map(row => {
      const game = teams.find(game => game.eventId === row.eventId);
      return <article className="nfl-total-card" key={row.selectionId || row.eventId} data-reviewed-rows aria-label={`${row.awayCode} at ${row.homeCode} over / under ${row.line}`}>
        <div className="nfl-total-status"><span className={`nfl-status is-${row.state}`}>{row.state === "post" ? "Final" : row.state === "in" ? "Live" : row.state === "pre" ? "Upcoming" : "Status unavailable"}</span><span>{kickoffLabel(row.kickoff || game?.kickoff)}</span></div>
        <div className="nfl-total-matchup"><span><img src={game?.awayLogo} alt={`${row.awayCode} logo`} width="30" height="30" />{row.awayCode}</span><small>at</small><span><img src={game?.homeLogo} alt={`${row.homeCode} logo`} width="30" height="30" />{row.homeCode}</span></div>
        <div className="nfl-total-line"><span>Printed total</span><strong>{row.line}</strong></div>
        <div className="nfl-total-user"><span>Your pick</span><strong>{row.userPick ? `${row.userPick} ${row.line}` : "Not recorded"}</strong>{row.userPick && <small className={row.userCorrect === true ? "is-correct" : row.userCorrect === false ? "is-miss" : ""}>{row.userCorrect === true ? "Won" : row.userCorrect === false ? "Lost" : row.actualOutcome === "Push" ? "Push" : "Pending"}{row.userReportedAfterKickoff ? " · Reported after kickoff" : ""}</small>}</div>
        {row.analysis ? <><div className="nfl-total-lean"><span>Model pick</span><strong>{row.analysis.lean === "Even" ? "No lean" : row.analysis.lean} · {row.line}</strong><span>{Math.round(Math.max(row.analysis.over_probability,row.analysis.under_probability)*100)}% · Experimental</span></div><p>Projected total: {row.projection.projected_total.toFixed(1)} · 80% range {row.projection.interval_80[0]}–{row.projection.interval_80[1]}</p>{row.analysis.push_probability > 0 && <p>Push: {Math.round(row.analysis.push_probability*100)}%</p>}</> : <p className="nfl-total-unavailable"><strong>Model pick: —</strong><br />No pregame forecast recorded</p>}
        <div className="nfl-total-result">{row.actualOutcome ? <><strong>{row.actualOutcome} · {row.actualTotal} points</strong><span>{row.correct === true ? "Model pick won" : row.correct === false ? "Model pick lost" : row.actualOutcome === "Push" ? "Push · separate from wins/losses" : row.analysis?.lean === "Even" ? "50/50 · excluded from pick record" : "No model pick to grade"}</span></> : <span>{row.liveTotal != null ? `Live combined score: ${row.liveTotal} · Not final` : "Awaiting final score"}</span>}</div>
        {game && <Button className="nfl-total-details" onClick={() => onDetails(game)} aria-label={`Game details for ${row.awayCode} at ${row.homeCode} total`}>Game details ↗</Button>}
      </article>;
    })}</div> : <p className="nfl-total-empty">Send your three matchups and their printed totals each week to add the next card.</p>}
    <p className="nfl-total-note">Send your three matchups and printed totals each week. Future cards use saved pregame model picks; games already underway receive no new prediction. Pushes stay separate. Contest settlement follows the card’s own rules.</p>
    </div>
  </DataComponent></>;
}

export function DashboardContent() {
  return new URL(window.location.href).searchParams.get("page") === "performance" ? <PerformanceContent /> : <MatchupsContent />;
}

function MatchupsContent() {
  const { snapshot, queries, visible } = useDataApp();
  const [status, setStatus] = useState("all");
  const [slate, setSlate] = useState("all");
  const [sort, setSort] = useState("live");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [locking, setLocking] = useState(false);
  const [tick, setTick] = useState(Date.now());
  const { job, refresh: refreshAnalysis, busy } = useAnalysisRefresh(snapshot.period?.week);
  useEffect(() => { const timer = setInterval(() => setTick(Date.now()), 15000); return () => clearInterval(timer); }, []);
  const all = queries.matchups?.rows || [];
  const brochure = queries.brochure?.rows || [];
  const filtered = useMemo(() => orderedGames(filterGames(all, { status, slate, search }), sort), [all, status, slate, search, sort]);
  const summary = gameSummary(filtered);
  const selectedRow = selected ? all.find(row => row.eventId === selected.eventId) || selected : null;
  const age = sourceAgeLabel(queries.matchups?.source?.executedAt || snapshot.generatedAt, tick);
  const stale = age.stale || snapshot.nflFeed?.status === "unavailable";
  const requestedWeek = Number(new URL(window.location.href).searchParams.get("week") || snapshot.period?.week);
  if (Number.isInteger(requestedWeek) && requestedWeek >= 1 && requestedWeek <= 18 && requestedWeek !== snapshot.period?.week) return <div className="nfl-dashboard nfl-empty" role="status"><strong>Loading Week {requestedWeek}…</strong><p>{snapshot.nflFeed?.error || "Checking the complete schedule and available data."}</p><a href="?view=1&tab=dashboard">Return to the saved week</a></div>;
  const marketPicks = all.map(row => row.marketTotal).filter(Boolean);
  const marketRecord = { wins: marketPicks.filter(row => row.correct === true).length, losses: marketPicks.filter(row => row.correct === false).length, picks: marketPicks.filter(row => row.originalPick).length };
  const spreadRecord = totalRecord(all.map(row => ({ ...row.marketSpread, analysis: row.marketSpread?.originalPick })));
  const spotlight = weeklyTossUp(all);
  const lockable = orderedGames(all.filter(row => row.state === "pre" && row.pick && !row.lock && Date.parse(row.kickoff) > tick), "kickoff");
  return <div className="nfl-dashboard">
    <NflViews active="games" />
    <div className="nfl-week-toolbar"><div className="nfl-week-label"><span className="nfl-season">{snapshot.period?.season} NFL season</span><label className="nfl-week-select"><span className="nfl-visually-hidden">NFL week</span><select aria-label="NFL week" value={snapshot.period?.week} onChange={event => {const url = new URL(window.location.href); url.searchParams.set("week", event.target.value); window.location.assign(url);}}>{Object.keys(snapshot.seasonSchedule || {[snapshot.period?.week]:[]}).map(week => <option key={week} value={week}>Week {week}</option>)}</select></label></div><div className="nfl-feed-controls"><span className={`nfl-feed-label ${stale ? "is-stale" : ""}`} role="status"><span className="nfl-feed-dot" />{stale ? "Last update" : snapshot.nflFeed?.status === "connected" ? "Scores & lines" : "Snapshot"} {age.text}</span><Button className="nfl-refresh-button" disabled={busy} onClick={refreshAnalysis} aria-label="Refresh data and analysis"><Icon name="refresh" />{busy ? "Refreshing…" : "Refresh data & analysis"}</Button></div></div>
    {job.message && <div className={`nfl-job-status is-${job.state}`} role="status">{job.week ? `Week ${job.week}: ` : ""}{job.message}</div>}
    {job.automation && <details className="nfl-automation"><summary>Automatic preparation · {job.automation.enabled ? "On" : "Off"}</summary><p>{job.automation.cadence}</p>{job.automation.nextCheckAt && <p>Next due: Week {job.automation.nextWeek} · {new Date(job.automation.nextCheckAt).toLocaleString("en-US", {timeZone:"America/New_York"})} ET</p>}<p>Opening the current week rechecks injuries, quarterbacks, coaches and weather when the last check is over two hours old, reusing the day's fitted model. Full statistics refits run daily (up to six scheduled and four manual per UTC day). Blocked pregame checks retry every ten minutes until their window closes.</p>{job.automation.error && <p role="status">{job.automation.error}</p>}{job.automation.recent?.[0]?.message && <p>Last scheduled attempt: Week {job.automation.recent[0].week} · {job.automation.recent[0].message}</p>}</details>}
    {snapshot.nflFeed?.error && <div className="nfl-feed-warning" role="status">Live updates are temporarily unavailable. Scores below retain their last successful update.</div>}
    <BackgroundLines collection={job.marketCollection} week={snapshot.period?.week} />
    <nav className="nfl-mobile-nav" aria-label="Dashboard sections"><a href="#nfl-matchups">Games · {all.length}</a>{brochure.length > 0 && visible("weekly-totals") && <a href="#nfl-weekly-totals">Printed card · {brochure.length}</a>}</nav>
    <TossUp spotlight={spotlight} onDetails={setSelected} />
    <p className="nfl-tracking-scope" data-reviewed-rows>All {all.length} games · Winners, totals and spreads<br />Market totals: {marketRecord.picks ? `${marketRecord.wins}–${marketRecord.losses} from ${marketRecord.picks} saved picks` : "No saved picks yet"}<br />Against the spread: {spreadRecord.selections ? `${spreadRecord.wins}–${spreadRecord.losses} · ${spreadRecord.pushes} pushes · ${spreadRecord.pending} pending` : "No saved picks yet"}</p>
    {visible("week-overview") && <DataComponent id="week-overview" queryId="matchups" title="This week" kind="custom" variant="plain" sourceRows={filtered} displayRows={filtered} className="nfl-overview-evidence"><div className="nfl-overview" data-reviewed-rows><div><span>Matchups shown</span><strong>{summary.games}</strong></div><div><span>Live now</span><strong className={summary.live ? "nfl-live-count" : ""}>{summary.live}</strong></div><div><span>Still to come</span><strong>{summary.upcoming}</strong></div><div><span>Original picks record</span><strong>{summary.decided ? `${summary.wins}–${summary.losses}` : "—"}</strong><small>{summary.decided ? `${summary.decided} completed ${summary.decided === 1 ? "pick" : "picks"}` : "No completed picks in this view"}</small></div></div></DataComponent>}
    {brochure.length > 0 && visible("weekly-totals") && <BrochureCard rows={brochure} teams={all} onDetails={setSelected} />}
    <span id="nfl-matchups" className="nfl-section-anchor" aria-hidden="true" />
    <SortableRegion id="nfl:matchups" variant="freeform" authoredRevision={1} className="nfl-matchup-region">
      <SortableItem id="weekly-games" label="Weekly matchups" kind="custom"><DataComponent id="weekly-games" queryId="matchups" title="Matchups" kind="custom" variant="plain" sourceRows={filtered} displayRows={filtered} description="Saved pregame predictions with current scores. Later revisions never change the original picks record." className="nfl-grid-evidence" headerControls={<div className="nfl-filter-controls"><SegmentedControl className="nfl-status-control" size="default" fullWidth ariaLabel="Game status" value={status} onChange={setStatus} options={[{ value: "all", ariaLabel: "All games", label: <><span className="nfl-filter-full">All games</span><span className="nfl-filter-short">All</span></> }, { value: "in", label: "Live" }, { value: "pre", ariaLabel: "Upcoming", label: <><span className="nfl-filter-full">Upcoming</span><span className="nfl-filter-short">Next</span></> }, { value: "post", label: "Final" }]} /></div>}>
        <div className="nfl-secondary-controls"><label className="nfl-search"><span className="nfl-visually-hidden">Search teams</span><input type="search" placeholder="Find a team or matchup…" value={search} onChange={event => setSearch(event.target.value)} /></label><div className="nfl-select-controls"><Dropdown label="Slate" showLabel triggerClassName="filter-trigger nfl-select-trigger" value={slate} onChange={setSlate} choices={["all", "sunmon"]} choiceLabels={{ all: "Full week", sunmon: "Sunday + Monday" }} /><Dropdown label="Sort" showLabel triggerClassName="filter-trigger nfl-select-trigger" value={sort} onChange={setSort} choices={["live", "kickoff", "confidence"]} choiceLabels={{ live: "Live first", kickoff: "Kickoff time", confidence: "Pick confidence" }} /></div></div>
        {filtered.length ? <div className="nfl-game-grid">{filtered.map(row => <GameCard key={row.eventId} row={row} onDetails={setSelected} />)}</div> : <div className="nfl-empty"><strong>No games match this view.</strong><p>Try another status, slate or team name.</p><Button onClick={() => { setStatus("all"); setSlate("all"); setSearch(""); }}>Show all games</Button></div>}
      </DataComponent></SortableItem>
    </SortableRegion>
    {lockable.length > 0 && <div className="nfl-lock-all"><span>{lockable.length} upcoming {lockable.length === 1 ? "game" : "games"} not yet locked</span><Button className="nfl-lock-button" onClick={() => setLocking(true)}>Lock in bets</Button></div>}
    <footer className="nfl-footer"><span>Team logos: NFL.com · Scores: ESPN</span><span>Preliminary picks require a final lineup check.</span></footer>
    <Dialog className="nfl-game-dialog" open={Boolean(selectedRow)} onClose={() => setSelected(null)} title={selectedRow ? `${selectedRow.awayName} at ${selectedRow.homeName}` : "Game details"}><Detail row={selectedRow} latest={selectedRow?.state === "pre" && job.week === snapshot.period?.week ? job.inputs?.find(input => input.eventId === selectedRow?.eventId) : null} now={tick} onClose={() => setSelected(null)} /></Dialog>
    <Dialog className="nfl-game-dialog" open={locking} onClose={() => setLocking(false)} title="Lock in bets">{locking && <LockDialog rows={lockable} week={snapshot.period?.week} onClose={() => setLocking(false)} />}</Dialog>
  </div>;
}
