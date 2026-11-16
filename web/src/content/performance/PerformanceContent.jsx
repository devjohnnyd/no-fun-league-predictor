import React, { useState } from "react";
import { Button, DataComponent, DataTable, EvidenceChart, chartConfigEntries, Dialog, SortableItem, SortableRegion, useDataApp } from "../../data-app-public.jsx";
import { combineWeeks, performanceHref, pickKinds, statusNames } from "./performance.mjs";
import "./performance.css";

const percent = value => value == null ? "—" : `${(100*value).toFixed(1)}%`;
const decimal = value => value == null ? "—" : value.toFixed(3);
const time = (value,precision) => !value ? "Not recorded" : precision === "date" ? `${value} · Date only` : `${new Date(value).toLocaleString("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})} ET`;
const outcome = row => row.status === "final" ? row.correct ? "Won" : "Lost" : statusNames[row.status];

export function NflViews({active}) {
  return <nav className="nfl-view-nav" aria-label="NFL views">{[["games","Games"],["performance","Season performance"]].map(([view,label])=><a key={view} href={performanceHref(view)} target={window.location.hostname === "johnnyd-ai-api.azurewebsites.net" ? "_top" : "_self"} aria-current={active===view ? "page" : undefined}>{label}</a>)}</nav>;
}

function Chart({id,title,queryId,rows,spec,description}) {
  const measures = Array.isArray(spec.y) ? spec.y : [spec.y];
  if (!rows.some(row=>measures.some(field=>Number.isFinite(row[field])))) return <DataComponent id={id} title={title} queryId={queryId} kind="custom" sourceRows={rows} displayRows={rows} description={description}><p className="nfl-performance-note">No settled picks to chart in this selection.</p></DataComponent>;
  const [chart] = chartConfigEntries({id,title,rows,spec:{...spec,yDomain:[0,100],stackable:false}});
  return <EvidenceChart id={id} title={title} queryId={queryId} rows={rows} sourceRows={rows} height={260} spec={chart.spec} description={description} />;
}

export function PerformanceContent() {
  const {snapshot,queries} = useDataApp();
  const [kind,setKind] = useState("winner");
  const [week,setWeek] = useState("all");
  const [status,setStatus] = useState("recorded");
  const [selected,setSelected] = useState(null);
  const ready = Boolean(queries["performance-picks"]);
  const weekly = (queries["performance-weeks"]?.rows||[]).filter(r=>r.kind===kind && (week==="all" || r.week===Number(week)));
  const trackedWeeks = weekly.filter(r=>r.recorded>0 || r.noPick>0 || r.abstained>0);
  const metrics = combineWeeks(weekly);
  const picks = (queries["performance-picks"]?.rows||[]).filter(r=>r.kind===kind && (week==="all" || r.week===Number(week)));
  const calibration = (queries["performance-calibration"]?.rows||[]).filter(r=>r.kind===kind && r.week===(week==="all" ? null : Number(week)));
  const source = queries["performance-picks"]?.source;
  const warnings = source?.warnings || [];
  const ledger = picks.filter(r=>status==="all" || (status==="recorded" ? r.pick && r.pick!=="Even" : status==="won" ? r.correct===true : status==="lost" ? r.correct===false : r.status===status)).map(r=>({...r,
    matchup:`${r.away} at ${r.home}`,choice:r.pick ? `${r.pick}${r.line!=null ? ` ${r.line}` : ""}` : "No saved pick",
    confidence:percent(r.probability),result:outcome(r),score:r.homeScore == null ? "—" : `${r.awayScore}–${r.homeScore}`,
    issueLabel:time(r.issuedAt,r.issuePrecision),revisionLabel:r.kind==="winner" && r.revisionCount ? `${r.latestPick} · ${percent(r.latestProbability)} (${r.revisionCount} revisions)` : "—"}));
  return <div className="nfl-performance"><NflViews active="performance" />
    <div className="nfl-performance-heading"><div><h2>Season performance</h2><p>{snapshot.period?.season} regular season · Recorded picks only</p></div><Button onClick={()=>window.dispatchEvent(new Event("nfl:refresh-scores"))}>Refresh results</Button></div>
    {snapshot.nflFeed?.status==="unavailable" && <p className="nfl-performance-warning" role="status">{snapshot.nflFeed.error}</p>}
    {!ready ? <div className="nfl-performance-empty" role="status">Loading saved picks and verified results…</div> : <>
    <div className="nfl-performance-filters"><label>Record<select aria-label="Performance record" value={kind} onChange={event=>{setKind(event.target.value);setStatus("recorded");setSelected(null);}}>{Object.entries(pickKinds).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>Week<select aria-label="Performance week" value={week} onChange={event=>{setWeek(event.target.value);setSelected(null);}}><option value="all">All weeks</option>{Array.from({length:18},(_,i)=><option key={i+1} value={i+1}>Week {i+1}</option>)}</select></label><span>{source?.executedAt ? `Oldest results check: ${time(source.executedAt)}` : "Result source time unavailable"}</span></div>
    {warnings.length>0 && <div className="nfl-performance-warning" role="status">{warnings.map(message=><p key={message}>{message}</p>)}</div>}
    <SortableRegion id="nfl:performance" variant="freeform" authoredRevision={1} label="Performance blocks">
    <SortableItem id="performance-metrics" label="Performance metrics" kind="custom"><DataComponent id="performance-metrics" title={`${pickKinds[kind]} · ${week==="all" ? "Season" : `Week ${week}`}`} queryId="performance-weeks" kind="custom" sourceRows={weekly} displayRows={[metrics]} description="Original recorded selections. Revisions never replace the first pick in these metrics.">
      <div className="nfl-performance-metrics" data-reviewed-rows><div><span>Original record</span><strong>{metrics.decided ? `${metrics.wins}–${metrics.losses}` : "—"}</strong><small>{metrics.recorded} recorded · {metrics.decided} decisive</small></div><div><span>Accuracy</span><strong>{percent(metrics.accuracy)}</strong><small>Wins ÷ decisive selections</small></div><div><span>Brier score</span><strong>{decimal(metrics.brier)}</strong><small>Lower is better · {metrics.probabilityGames} games</small></div><div><span>Log loss</span><strong>{decimal(metrics.logLoss)}</strong><small>Lower is better · {metrics.probabilityGames} games</small></div></div>
      <p className="nfl-performance-counts" data-reviewed-rows>{metrics.pending} pending · {metrics.ties} ties · {metrics.pushes} pushes · {metrics.abstained} no lean · {metrics.noPick} without a pick · {metrics.unavailable} results unavailable</p>
    <p className="nfl-performance-note">{kind==="printed-user" ? `${metrics.reportedLate} choices were reported after kickoff; placement times are unknown. These are user-reported results, separate from model performance. No probabilities were recorded.` : <>Brier score measures squared probability error; log loss penalizes confident misses. {kind!=="winner" && "Total probabilities condition on no push. "}Ties, pushes, pending games and missing picks are excluded from decisive accuracy. Early results are a small sample.</>}</p>
    </DataComponent></SortableItem>
    <SortableItem id="performance-charts" label="Performance charts" kind="custom"><div className="nfl-performance-charts"><Chart id="performance-weekly-chart" title="Weekly accuracy (%)" queryId="performance-weeks" rows={weekly.filter(r=>r.recorded>0)} spec={{type:"bar",x:"weekLabel",y:"accuracyPct"}} description="Each bar uses that week's decisive original picks; weeks without settled picks have no accuracy." />
      {kind!=="printed-user" && <Chart id="performance-calibration-chart" title="Confidence versus results (%)" queryId="performance-calibration" rows={calibration} spec={{type:"bar",x:"band",y:["meanConfidence","hitRate"]}} description="Average predicted chance and actual win rate in each confidence band. Labels show the number of decisive picks; this is descriptive, not proof of reliability." />}</div></SortableItem>
    <SortableItem id="performance-weekly-table" label="Weekly record" kind="custom"><DataComponent id="performance-weekly-table" title="Weekly record" queryId="performance-weeks" kind="table" sourceRows={trackedWeeks} displayRows={trackedWeeks} description="Tracked weeks only. Weeks without a saved pick remain unscored."><DataTable caption="Weekly original pick record" searchable={false} rows={trackedWeeks.map(r=>({...r,record:r.decided ? `${r.wins}–${r.losses}` : "—",accuracyLabel:percent(r.accuracy),brierLabel:decimal(r.brier)}))} columns={[{field:"weekLabel",label:"Week"},{field:"recorded",label:"Recorded"},{field:"record",label:"W–L"},{field:"accuracyLabel",label:"Accuracy"},{field:"brierLabel",label:"Brier"},{field:"pending",label:"Pending"}]} /></DataComponent></SortableItem>
    <SortableItem id="performance-ledger" label="Pick ledger" kind="custom"><DataComponent id="performance-ledger" title="Pick ledger" queryId="performance-picks" kind="table" sourceRows={picks} displayRows={ledger} description="Select a row to inspect the original pick, exact line, result receipt and latest winner revision.">
      <label className="nfl-ledger-filter">Show<select aria-label="Pick ledger status" value={status} onChange={event=>setStatus(event.target.value)}><option value="recorded">Recorded directional picks</option><option value="all">All tracked entries</option><option value="won">Won</option><option value="lost">Lost</option><option value="pending">Pending</option><option value="no-pick">Without a pick</option></select></label>
      <DataTable caption="Recorded picks and results" rows={ledger} rowKey="selectionId" onRowSelect={setSelected} rowActionLabel={r=>`Inspect ${r.matchup} ${r.choice}`} columns={[{field:"week",label:"Week"},{field:"matchup",label:"Matchup"},{field:"choice",label:"Original pick"},{field:"confidence",label:"Chance"},{field:"result",label:"Result"},{field:"issueLabel",label:"Recorded"},{field:"revisionLabel",label:"Latest winner revision"}]} />
    </DataComponent></SortableItem></SortableRegion>
    </>}
    <Dialog open={Boolean(selected)} onClose={()=>setSelected(null)} title={selected ? `${selected.away} at ${selected.home} · Original selection` : "Pick details"} className="nfl-performance-dialog">{selected && <div className="nfl-performance-detail" data-reviewed-rows><dl>{[["Original pick",selected.choice],["Recorded",selected.issueLabel],["Chance",selected.confidence],["Result",selected.result],["Final score (away–home)",selected.score],["Provider",selected.provider || "Not applicable"],["Model",selected.model || "Experimental totals / user choice"],["Latest winner revision",selected.revisionLabel],["Latest revision recorded",selected.revisionCount ? time(selected.latestIssuedAt) : "—"]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>{selected.reportedAfterKickoff && <p>Reported after kickoff; original placement time is unknown.</p>}{selected.forecastSource?.sha256 && <p className="nfl-receipt">Forecast: {selected.forecastSource.label}<br />SHA-256: {selected.forecastSource.sha256}</p>}{selected.quoteSource?.url && <p><a href={selected.quoteSource.url} target="_blank" rel="noreferrer">Original quote source</a> · {time(selected.quoteSource.retrieved_at)}</p>}{selected.resultSource?.url && <p><a href={selected.resultSource.url} target="_blank" rel="noreferrer">Results source</a> · {time(selected.resultRetrievedAt)}</p>}{selected.cardSource && <p>{selected.cardSource}</p>}<Button onClick={()=>setSelected(null)}>Back to performance</Button></div>}</Dialog>
  </div>;
}
