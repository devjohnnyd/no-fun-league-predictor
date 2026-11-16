import test from "node:test";
import assert from "node:assert/strict";
import {combineWeeks,performanceHref,validatePerformance} from "../web/src/content/performance/performance.mjs";

test("season rates use game counts rather than averaging weekly rates",()=>{
  const metrics = combineWeeks([{wins:1,losses:0,decided:1,probabilityGames:1,brier:.04,logLoss:.2},{wins:1,losses:8,decided:9,probabilityGames:9,brier:.5,logLoss:1.2}]);
  assert.equal(metrics.accuracy,.2);
  assert.equal(metrics.wins,2);
  assert.equal(metrics.losses,8);
  assert.equal(metrics.probabilityGames,10);
  assert.ok(Math.abs(metrics.brier-.454)<1e-12);
  assert.ok(Math.abs(metrics.logLoss-1.1)<1e-12);
  assert.equal(combineWeeks([]).accuracy,null);
  assert.equal(combineWeeks([]).brier,null);
});

test("navigation stays local in previews and uses the unlisted hosted routes in production",()=>{
  assert.equal(performanceHref("performance",{hostname:"localhost"}),"?page=performance&view=1&tab=dashboard");
  assert.equal(performanceHref("performance",{hostname:"johnnyd-ai-api.azurewebsites.net"}),"https://www.johnnyd.ai/nfl/performance/");
});

test("refresh rejects incomplete, wrong-season and duplicate performance evidence",()=>{
  const queries = Object.fromEntries(["performance-picks","performance-summary","performance-weeks","performance-calibration"].map(key=>[key,{rows:[],source:{scope:"Recorded picks"}}]));
  const kinds = ["winner","market","printed-model","printed-user"];
  queries["performance-summary"].rows = kinds.map(kind=>({kind,...combineWeeks([])}));
  queries["performance-weeks"].rows = kinds.flatMap(kind=>Array.from({length:18},(_,index)=>({kind,week:index+1,...combineWeeks([])})));
  const value = {season:2026,generatedAt:"2026-11-16T20:00:00Z",queries};
  validatePerformance(value,2026);
  assert.throws(()=>validatePerformance(value,2025));
  assert.throws(()=>validatePerformance({...value,queries:{}},2026));
  const pick = {selectionId:"one",season:2026,week:10,eventId:"1",home:"BAL",away:"LAC",kind:"winner",status:"final",probability:.7};
  queries["performance-picks"].rows = [pick,pick];
  assert.throws(()=>validatePerformance(value,2026));
  queries["performance-picks"].rows = [{...pick,probability:NaN}];
  assert.throws(()=>validatePerformance(value,2026));
  queries["performance-picks"].rows = [];
  queries["performance-summary"].rows[0].recorded=1;
  assert.throws(()=>validatePerformance(value,2026));
});
