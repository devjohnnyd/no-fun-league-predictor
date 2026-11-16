import fs from 'node:fs/promises';

const season=2026, asOf='2026-11-10', initial=1500, k=32, homeAdvantage=55, scale=400;
const events=[];
for(let week=1;week<=18;week++) {
  const raw=JSON.parse(await fs.readFile(new URL(`week${week}.json`,import.meta.url),'utf8'));
  for(const e of raw.events) {
    if(e.season.year!==season || e.season.type!==2 || e.week.number!==week) throw Error('Unexpected season/week');
    events.push(e);
  }
}
if(events.length!==272 || new Set(events.map(e=>e.id)).size!==272) throw Error('Schedule coverage/duplicate issue');
const localDate=d=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Indianapolis',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(d));
const localTime=d=>new Intl.DateTimeFormat('en-US',{timeZone:'America/Indianapolis',hour:'numeric',minute:'2-digit'}).format(new Date(d));
const games=events.map(e=>{
  const c=e.competitions[0], h=c.competitors.find(x=>x.homeAway==='home'), a=c.competitors.find(x=>x.homeAway==='away');
  const finished=e.status.type.completed && localDate(e.date)<=asOf;
  return {id:e.id,week:e.week.number,date:localDate(e.date),time:localTime(e.date),kickoff:e.date,
    home:h.team.abbreviation,away:a.team.abbreviation,homeName:h.team.displayName,awayName:a.team.displayName,
    homeId:h.team.id,awayId:a.team.id,homeScore:finished?Number(h.score):null,awayScore:finished?Number(a.score):null,
    status:finished?'Final':e.status.type.name==='STATUS_SCHEDULED'?'Scheduled':e.status.type.description,
    neutral:!!c.neutralSite,venue:c.venue?.fullName??'',broadcast:c.broadcast??'',
    source:e.links.find(x=>x.rel.includes('summary'))?.href??e.links[0]?.href,
    feed:`https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week=${e.week.number}&limit=1000`,
    reportedHomeRecord:h.records?.find(x=>x.type==='total')?.summary,reportedAwayRecord:a.records?.find(x=>x.type==='total')?.summary};
}).sort((a,b)=>a.kickoff.localeCompare(b.kickoff)||a.id.localeCompare(b.id));
const teams={};
for(const g of games) for(const side of ['home','away']) {
  const code=g[side];
  teams[code]??={code,name:g[side+'Name'],elo:initial,wins:0,losses:0,ties:0,played:0,pointsFor:0,pointsAgainst:0,results:[]};
}
if(Object.keys(teams).length!==32) throw Error('Team coverage');
for(const t of Object.values(teams)) if(games.filter(g=>g.home===t.code||g.away===t.code).length!==17) throw Error('Incomplete team schedule: '+t.code);
const pHome=(h,a,neutral)=>1/(1+10**((a-h-(neutral?0:homeAdvantage))/scale));
const weekly=[];
for(let week=1;week<=18;week++) {
  const completed=games.filter(g=>g.week===week && g.status==='Final');
  if(!completed.length) continue;
  const updates={};
  for(const g of completed) {
    if(!Number.isInteger(g.homeScore)||!Number.isInteger(g.awayScore)||g.homeScore<0||g.awayScore<0) throw Error('Invalid final score');
    const h=teams[g.home],a=teams[g.away];
    g.homeEloBefore=h.elo;g.awayEloBefore=a.elo;g.homeProb=pHome(h.elo,a.elo,g.neutral);
    g.result=g.homeScore>g.awayScore?1:g.homeScore<g.awayScore?0:0.5;
    g.winner=g.result===0.5?'Tie':g.result===1?g.home:g.away;
    g.modelPick=g.homeProb>=0.5?g.home:g.away;
    g.correct=g.result===0.5?null:Number(g.modelPick===g.winner);
    g.homeCorrect=g.result===0.5||g.neutral?null:Number(g.winner===g.home);
    g.brier=g.result===0.5?null:(g.homeProb-g.result)**2;
    g.logLoss=g.result===0.5?null:-(g.result*Math.log(g.homeProb)+(1-g.result)*Math.log(1-g.homeProb));
    const change=k*(g.result-g.homeProb);
    updates[g.home]=(updates[g.home]??0)+change;updates[g.away]=(updates[g.away]??0)-change;
    for(const [t,own,opp,res] of [[h,g.homeScore,g.awayScore,g.result],[a,g.awayScore,g.homeScore,1-g.result]]) {
      t.played++;t.pointsFor+=own;t.pointsAgainst+=opp;
      if(res===1)t.wins++;else if(res===0)t.losses++;else t.ties++;
      t.results.push(res===1?'W':res===0?'L':'T');
    }
  }
  for(const [code,change] of Object.entries(updates)) teams[code].elo+=change;
  const decided=completed.filter(g=>g.correct!==null);
  weekly.push({week,games:completed.length,ties:completed.length-decided.length,scored:decided.length,
    correct:decided.reduce((s,g)=>s+g.correct,0),brier:decided.reduce((s,g)=>s+g.brier,0)/decided.length});
}
const finals=games.filter(g=>g.status==='Final'), decided=finals.filter(g=>g.correct!==null), domestic=decided.filter(g=>!g.neutral);
const metrics={games:finals.length,ties:finals.length-decided.length,scored:decided.length,
  correct:decided.reduce((s,g)=>s+g.correct,0),accuracy:decided.reduce((s,g)=>s+g.correct,0)/decided.length,
  brier:decided.reduce((s,g)=>s+g.brier,0)/decided.length,logLoss:decided.reduce((s,g)=>s+g.logLoss,0)/decided.length,
  domesticGames:domestic.length,domesticModelCorrect:domestic.reduce((s,g)=>s+g.correct,0),
  domesticHomeCorrect:domestic.reduce((s,g)=>s+g.homeCorrect,0),latestGame:finals.at(-1).date};
const n=metrics.scored, p=metrics.accuracy, z=1.96, den=1+z*z/n;
metrics.accuracy95Low=(p+z*z/(2*n)-z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/den;
metrics.accuracy95High=(p+z*z/(2*n)+z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/den;
const forecasts=games.filter(g=>g.status==='Scheduled'&&['2026-11-15','2026-11-16'].includes(g.date)).map(g=>{
  const homeElo=teams[g.home].elo,awayElo=teams[g.away].elo,homeProb=pHome(homeElo,awayElo,g.neutral);
  return {...g,homeElo,awayElo,homeProb,pick:homeProb>=.5?g.home:g.away,pickProbability:Math.max(homeProb,1-homeProb)};
});
if(forecasts.length!==13) throw Error('Unexpected upcoming slate');
const sum=(key)=>Object.values(teams).reduce((s,t)=>s+t[key],0);
if(sum('played')!==2*finals.length || sum('pointsFor')!==sum('pointsAgainst') || Math.abs(sum('elo')-32*initial)>1e-8) throw Error('Reconciliation failed');
const sample=finals.find(g=>g.away==='BUF'&&g.home==='MIN'&&g.week===9);
if(sample.awayScore!==23||sample.homeScore!==6) throw Error('Official gamebook cross-check mismatch');
const data={season,asOf,retrievedAt:new Date().toISOString(),params:{initial,k,homeAdvantage,scale},games,teams:Object.values(teams).sort((a,b)=>b.elo-a.elo),weekly,metrics,forecasts,
  notes:['Regular season only. Preseason and playoffs are excluded.','All 272 scheduled games are included. Scores exist only for completed games as of November 10, 2026.',
  'Elo v1: all teams start at 1500. K=32, home advantage=55 Elo, logistic scale=400. Fixed defaults, not fitted or tuned to these results.',
  'Historical predictions freeze ratings at the start of each NFL week, then update after that week. No same-week outcome enters its own prediction.',
  'Ties update Elo as half a win. Ties are excluded from winner accuracy, binary Brier score and log loss. Win estimates do not explicitly model ties.',
  'Neutral venues get zero home advantage, including Patriots-Lions in Munich.',
  'Results-only baseline. No injuries, starting quarterbacks, weather, rest, betting lines or prior-season ratings are included.',
  'Model probabilities are uncalibrated estimates. Historical reconstruction is not an independently held-out test or a record of live forecasts.',
  'The November 10 forecast snapshot should be retained when refreshing, so later picks cannot overwrite the original picks.',
  'For an update, ask to refresh this tracker after the next games. No background refresh has been scheduled.'],
  validation:{uniqueGames:272,teams:32,gamesPerTeam:17,pointsReconcile:true,eloConserved:true,officialSamples:['Week 1: NE 10 SEA 13; SF 27 LAR 7 (NFL weekly schedule)','Week 9: BUF 23 MIN 6 (NFL official gamebook)'],sourceScope:'ESPN weekly scoreboards, season 2026, type 2, weeks 1-18'}};
await fs.writeFile(new URL('analysis.json',import.meta.url),JSON.stringify(data,null,2));
console.log(JSON.stringify({metrics,forecast:forecasts.map(g=>({game:g.away+' @ '+g.home,pick:g.pick,p:g.pickProbability})),topTeams:data.teams.slice(0,5).map(t=>({team:t.code,elo:t.elo,record:`${t.wins}-${t.losses}-${t.ties}`}))},null,2));
