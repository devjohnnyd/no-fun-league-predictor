export const pickKinds = {winner:"Winner picks",market:"Market totals","printed-model":"Printed card model","printed-user":"Your printed card picks"};
export const statusNames = {final:"Settled",pending:"Pending",tie:"Tie",push:"Push","no-pick":"No saved pick",abstained:"No lean",unavailable:"Result unavailable"};

export function combineWeeks(rows) {
  const result = Object.fromEntries(["recorded","decided","wins","losses","pending","unavailable","ties","pushes","noPick","abstained","reportedLate","probabilityGames"].map(key=>[key,rows.reduce((sum,row)=>sum+(row[key]||0),0)]));
  result.accuracy = result.decided ? result.wins/result.decided : null;
  for (const [key,field] of [["brier","brier"],["logLoss","logLoss"]])
    result[key] = result.probabilityGames ? rows.reduce((sum,row)=>sum+(row[field]??0)*(row.probabilityGames||0),0)/result.probabilityGames : null;
  return result;
}

export function performanceHref(view, location=window.location) {
  if (location.hostname === "johnnyd-ai-api.azurewebsites.net") return `https://www.johnnyd.ai/nfl/${view === "performance" ? "performance/" : ""}`;
  return view === "performance" ? "?page=performance&view=1&tab=dashboard" : "?view=1&tab=dashboard";
}

export function validatePerformance(next, season) {
  if (next?.season !== season || !Number.isFinite(Date.parse(next.generatedAt))) throw new Error("Performance feed scope or timestamp is invalid.");
  for (const key of ["performance-picks","performance-summary","performance-weeks","performance-calibration"])
    if (!Array.isArray(next.queries?.[key]?.rows) || !next.queries[key].source) throw new Error("Performance feed is incomplete.");
  const ids = new Set();
  for (const row of next.queries["performance-picks"].rows) {
    if (row.season !== season || !Number.isInteger(row.week) || row.week<1 || row.week>18 || !row.eventId || !row.home || !row.away || !pickKinds[row.kind] || !statusNames[row.status] || !row.selectionId || ids.has(row.selectionId))
      throw new Error("Performance feed contains conflicting selections.");
    if (row.probability != null && (!Number.isFinite(row.probability) || row.probability<0 || row.probability>1)) throw new Error("Performance probability is invalid.");
    ids.add(row.selectionId);
  }
  const summaries = next.queries["performance-summary"].rows;
  if (summaries.length !== 4 || new Set(summaries.map(row=>row.kind)).size !== 4 || summaries.some(row=>!pickKinds[row.kind]))
    throw new Error("Performance summary is incomplete.");
  const weekly = next.queries["performance-weeks"].rows;
  if (weekly.length !== 72 || new Set(weekly.map(row=>`${row.kind}:${row.week}`)).size !== 72)
    throw new Error("Weekly performance coverage is incomplete.");
  const counts = ["recorded","decided","wins","losses","pending","unavailable","ties","pushes","noPick","abstained","reportedLate","probabilityGames"];
  for (const row of [...summaries,...weekly]) {
    if (!pickKinds[row.kind] || (row.week != null && (!Number.isInteger(row.week) || row.week<1 || row.week>18)) || counts.some(key=>!Number.isInteger(row[key]) || row[key]<0) || row.decided!==row.wins+row.losses || row.recorded!==row.decided+row.pending+row.ties+row.pushes+row.unavailable || row.probabilityGames>row.decided)
      throw new Error("Performance counts do not reconcile.");
  }
  for (const row of summaries) {
    const combined = combineWeeks(weekly.filter(item=>item.kind===row.kind));
    if (counts.some(key=>row[key]!==combined[key]) || ["accuracy","brier","logLoss"].some(key=>row[key] == null ? combined[key] != null : !Number.isFinite(row[key]) || combined[key] == null || Math.abs(row[key]-combined[key])>1e-9))
      throw new Error("Season metrics differ from weekly evidence.");
    if (row.recorded !== next.queries["performance-picks"].rows.filter(item=>item.kind===row.kind && item.pick && item.pick!=="Even").length)
      throw new Error("Pick ledger differs from the reported record.");
  }
}
