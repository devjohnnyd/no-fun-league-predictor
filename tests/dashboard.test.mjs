import test from "node:test";
import assert from "node:assert/strict";
import { filterGames, gameSummary, orderedGames, sourceAgeLabel, totalRecord, validateMatchupRefresh } from "../web/src/content/dashboard/football.mjs";

const rows = [
  { eventId: "1", state: "post", kickoff: "2026-11-15T18:00Z", homeName: "Jets", awayName: "Bills", homeCode: "NYJ", awayCode: "BUF", slateEligible: true, originalCorrect: true, pickProbability: .75 },
  { eventId: "2", state: "pre", kickoff: "2026-11-17T01:15Z", homeName: "Ravens", awayName: "Chargers", homeCode: "BAL", awayCode: "LAC", slateEligible: true, originalCorrect: null, pickProbability: .64 },
  { eventId: "3", state: "post", kickoff: "2026-11-13T01:15Z", homeName: "Giants", awayName: "Commanders", homeCode: "NYG", awayCode: "WSH", slateEligible: false, originalCorrect: null, pickProbability: null },
];

test("total records separate user picks, model abstentions, pushes and pending games", () => {
  const totals = [
    { userPick: "Over", userCorrect: false, correct: true, actualOutcome: "Under", analysis: { lean: "Under" } },
    { userPick: "Over", userCorrect: true, correct: null, actualOutcome: "Over", analysis: null },
    { userPick: "Over", userCorrect: null, correct: null, actualOutcome: "Push", analysis: { lean: "Over" } },
    { userPick: null, userCorrect: null, correct: null, actualOutcome: null, analysis: { lean: "Under" } },
    { userPick: null, userCorrect: null, correct: null, actualOutcome: "Over", analysis: { lean: "Even" } },
  ];
  assert.deepEqual(totalRecord(totals), { selections: 3, wins: 1, losses: 0, pushes: 1, pending: 1, unavailable: 1, abstentions: 1 });
  assert.deepEqual(totalRecord(totals, "user"), { selections: 3, wins: 1, losses: 1, pushes: 1, pending: 0, unavailable: 2, abstentions: 0 });
});

test("filters intersect and clearing them restores the full population", () => {
  assert.equal(filterGames(rows, { search: "BUF" }).length, 1);
  assert.equal(filterGames(rows, { slate: "sunmon" }).length, 2);
  assert.equal(filterGames(rows, { status: "pre", search: "Bills" }).length, 0);
  assert.equal(filterGames(rows, {}).length, 3);
});
test("pending games and games without picks cannot become losses", () => {
  assert.deepEqual(gameSummary(rows), { games: 3, live: 0, upcoming: 1, decided: 1, wins: 1, losses: 0 });
});
test("live-first ordering does not mutate source rows", () => {
  assert.equal(orderedGames(rows)[0].eventId, "2");
  assert.equal(rows[0].eventId, "1");
});
test("stale and missing source times stay visibly stale", () => {
  assert.equal(sourceAgeLabel("2026-11-15T18:00Z", Date.parse("2026-11-15T18:03Z")).stale, true);
  assert.equal(sourceAgeLabel(null).stale, true);
});

test("a partial static score feed cannot replace the reviewed slate", () => {
  assert.throws(() => validateMatchupRefresh(rows, rows.slice(0, 1)), /incomplete/);
  assert.throws(() => validateMatchupRefresh(rows, []), /incomplete/);
  assert.equal(rows.length, 3);
});
test("refreshed game identities must match, including duplicates and home/away", () => {
  assert.throws(() => validateMatchupRefresh(rows, [rows[0], rows[0], rows[2]]), /identities/);
  assert.throws(() => validateMatchupRefresh(rows, rows.map((r,i) => i === 2 ? {...r, homeCode:"BAL"} : r)), /identities/);
  assert.throws(() => validateMatchupRefresh(rows, rows.map((r,i) => i === 2 ? {...r, eventId:"new"} : r)), /identities/);
});
test("complete reordered score updates are accepted without changing the old snapshot", () => {
  const next = [...rows].reverse().map(row => ({...row, homeScore:24, awayScore:17}));
  assert.doesNotThrow(() => validateMatchupRefresh(rows, next));
  assert.equal(rows[0].homeScore, undefined);
});
