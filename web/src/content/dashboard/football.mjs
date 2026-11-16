export function filterGames(rows, { status = "all", slate = "all", search = "" } = {}) {
  const text = search.trim().toLocaleLowerCase();
  return rows.filter(row => (status === "all" || row.state === status) && (slate === "all" || row.slateEligible) &&
    (!text || `${row.homeName} ${row.awayName} ${row.homeCode} ${row.awayCode}`.toLocaleLowerCase().includes(text)));
}
export function orderedGames(rows, mode = "live") {
  const rank = { in: 0, pre: 1, post: 2, unknown: 3 };
  return [...rows].sort((a, b) => {
    if (mode === "live" && rank[a.state] !== rank[b.state]) return (rank[a.state] ?? 3) - (rank[b.state] ?? 3);
    if (mode === "confidence" && a.pickProbability !== b.pickProbability) return (b.pickProbability ?? -1) - (a.pickProbability ?? -1);
    return Date.parse(a.kickoff) - Date.parse(b.kickoff) || a.eventId.localeCompare(b.eventId);
  });
}
export function gameSummary(rows) {
  const decided = rows.filter(row => row.originalCorrect != null);
  return { games: rows.length, live: rows.filter(row => row.state === "in").length,
    upcoming: rows.filter(row => row.state === "pre").length, decided: decided.length,
    wins: decided.filter(row => row.originalCorrect === true).length,
    losses: decided.filter(row => row.originalCorrect === false).length };
}
export function kickoffLabel(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Kickoff unavailable";
  return `${new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }).format(date)} ET`;
}
export function predictionLabel(row) {
  return row.predictionStage === "preliminary" ? "Preliminary" : row.predictionStage === "final" ? "Final pick" : "Original pick";
}
export function sourceAgeLabel(value, now = Date.now()) {
  const difference = (now - Date.parse(value)) / 1000;
  if (!Number.isFinite(difference) || difference < -30) return { text: "time unavailable", stale: true };
  const age = Math.max(0, difference);
  return { text: age < 60 ? "just now" : age < 3600 ? `${Math.floor(age / 60)}m ago` : age < 86400 ? `${Math.floor(age / 3600)}h ago` : `${Math.floor(age / 86400)}d ago`, stale: age > 120 };
}
export function validateMatchupRefresh(currentRows, nextRows) {
  if (!Array.isArray(currentRows) || !currentRows.length || !Array.isArray(nextRows) || nextRows.length !== currentRows.length)
    throw new Error("Score feed is incomplete. Showing the last complete slate.");
  const expected = new Map(currentRows.map(row => [row.eventId, row]));
  const ids = new Set();
  for (const row of nextRows) {
    const previous = expected.get(row.eventId);
    if (!previous || ids.has(row.eventId) || row.homeCode !== previous.homeCode || row.awayCode !== previous.awayCode)
      throw new Error("Score feed game identities changed. Showing the last complete slate.");
    ids.add(row.eventId);
  }
}
