import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
process.on('uncaughtException',e=>{console.error(e.message);process.exit(1)});
const path=u=>u.pathname.replace(/^\/([A-Za-z]:)/,'$1');
const data=JSON.parse(await fs.readFile(new URL('model.json',import.meta.url),'utf8'));
const base=JSON.parse(await fs.readFile(new URL('../analysis.json',import.meta.url),'utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path(new URL('original-tracker.xlsx',import.meta.url))));
const picks=wb.worksheets.getItem('Predictions'),teams=wb.worksheets.getItem('Teams'),games=wb.worksheets.getItem('Games'),perf=wb.worksheets.getItem('Performance');
const model=wb.worksheets.add('Model 2'),qbs=wb.worksheets.add('QB analysis'),factors=wb.worksheets.add('Matchup factors'),inj=wb.worksheets.add('Injuries'),coaches=wb.worksheets.add('Coaching');
const navy='#17324D',muted='#53677B',gold='#FFF4D1',blue='#E8F0F8';
function setup(s,title,lastCol,lastRow,widths){s.showGridLines=false;s.getRange(`A1:${lastCol}${lastRow}`).format.font={name:'Arial',size:10,color:'#183044'};s.getRange(`A1:${lastCol}${lastRow}`).format.rowHeight=23;s.getRange(`A1:${lastCol}${lastRow}`).format.verticalAlignment='center';s.getRange('A2').values=[[title]];s.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:navy};s.getRange(`A3:${lastCol}3`).format.borders={bottom:{style:'thin',color:'#9CB0C2'}};widths.forEach((w,i)=>s.getRangeByIndexes(0,i,lastRow,1).format.columnWidth=w);}
function header(s,row,values,start=0){const r=s.getRangeByIndexes(row-1,start,1,values.length);r.values=[values];r.format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true};r.format.rowHeight=38;}
function note(s,row,value){s.getRange(`A${row}`).values=[[value]];s.getRange(`A${row}`).format.font={name:'Arial',size:10,color:muted};}
function table(s,range,name){s.tables.add(range,true,name);}
function excelDate(d){return Date.parse(d+'T00:00:00Z')/86400000+25569;}
function time(t){const m=t.match(/(\d+):(\d+)\s*(AM|PM)/);return ((Number(m[1])%12+(m[3]==='PM'?12:0))*60+Number(m[2]))/1440;}
const end=278,gr=c=>`'Games'!$${c}$7:$${c}$${end}`;
const rowById=Object.fromEntries(base.games.map((g,i)=>[g.id,i+7]));
const testById=Object.fromEntries(data.backtest.map(g=>[g.espn,g]));
const forecastById=Object.fromEntries(data.forecast.map((g,i)=>[g.espn_id,{...g,modelRow:i+8}]));
const selectedEval=data.evaluations.find(e=>e.model===data.selected.model);
const labels={home_field:'Home field',off_epa_diff:'Offensive EPA',def_epa_diff:'Defensive EPA allowed',recent_net_diff:'Recent net EPA',qb_epa_diff:'QB EPA',qb_cpoe_diff:'QB CPOE',qb_experience_diff:'QB NFL experience',qb_new_diff:'QB small sample',sack_rate_diff:'Sacks allowed',def_sack_diff:'Defensive sack rate',explosive_diff:'Explosive plays',rest_diff:'Rest days',new_coach_diff:'New head coach',ol_out_diff:'Unavailable OL workload',skill_out_diff:'Unavailable skill workload',def_out_diff:'Unavailable defense workload',questionable_diff:'Questionable workload',wind_pass_diff:'Wind × pass tendency',cold_pass_diff:'Cold × pass tendency'};
const definitions={home_field:'1 at home, 0 neutral',off_epa_diff:'Home minus away, EPA/play',def_epa_diff:'Home minus away EPA allowed/play. Lower is better.',recent_net_diff:'Last four games, net EPA/play, shrunk toward 0',qb_epa_diff:'Home minus away QB EPA/dropback, shrunk toward 0',qb_cpoe_diff:'Home minus away completion over expectation, percentage points',qb_experience_diff:'Difference in log(1 + recency-weighted prior dropbacks)',qb_new_diff:'1 if home QB has <30 effective dropbacks, minus away flag',sack_rate_diff:'Home minus away fraction of dropbacks sacked',def_sack_diff:'Home minus away fraction of opposing dropbacks sacked',explosive_diff:'Home minus away explosive play fraction',rest_diff:'Home minus away rest days, capped at +/-7',new_coach_diff:'Home first-year HC indicator minus away',ol_out_diff:'Difference in unavailable OL prior four team-game snap shares',skill_out_diff:'Difference in unavailable RB/WR/TE/FB snap shares',def_out_diff:'Difference in unavailable defensive snap shares',questionable_diff:'Difference in non-QB questionable snap shares',wind_pass_diff:'Outdoor wind / 15 mph × home-minus-away pass rate',cold_pass_diff:'Outdoor max(45F - temperature, 0) / 20 × pass-rate difference'};
setup(model,'Expanded prediction model','U',137,[24,24,...Array(19).fill(15)]);
note(model,4,'Model 2.0. Logistic regression with 19 inputs. Regularization chosen on 2025. Final fit: '+data.quality.training_games+' decisive games.');
model.getRange('A5:B5').values=[['Intercept',data.model.beta[0]]];model.getRange('D5:E5').values=[['Penalty',data.selected.alpha]];
header(model,7,['Game ID','Away','Home','Home log odds','Home win estimate']);
header(model,25,['Feature','Training mean','Training SD','Coefficient','Meaning']);
model.getRange('A26:E44').values=data.model.names.map((n,i)=>[labels[n],data.model.mean[i],data.model.std[i],data.model.beta[i+1],definitions[n]]);
model.getRange('B26:D44').setNumberFormat('0.0000');model.getRange('E26:E44').format.columnWidth=70;
header(model,50,['Game ID','Matchup',...data.model.names.map(n=>labels[n])]);
header(model,68,['Game ID','Matchup',...data.model.names.map(n=>labels[n])]);
for(let i=0;i<data.forecast.length;i++){
 const g=data.forecast[i],r=i+8,raw=i+51,cr=i+69;
 model.getRange(`A${r}:C${r}`).values=[[g.espn_id,g.away,g.home]];
 model.getRange(`D${r}:E${r}`).formulas=[[`=$B$5+SUM(C${cr}:U${cr})`,`=1/(1+EXP(-D${r}))`]];
 model.getRange(`A${raw}:U${raw}`).values=[[g.espn_id,g.away+' @ '+g.home,...data.model.names.map(n=>g.features[n])]];
 model.getRange(`A${cr}:B${cr}`).values=[[g.espn_id,g.away+' @ '+g.home]];
 for(let j=0;j<19;j++)model.getCell(cr-1,j+2).formulas=[[`=(${letter(j+2)}${raw}-$B$${j+26})/$C$${j+26}*$D$${j+26}`]];
}
model.getRange('E8:E20').setNumberFormat('0.0%');model.getRange('D8:D20').setNumberFormat('0.000');model.getRange('C51:U63').format.fill=gold;model.getRange('C51:U81').setNumberFormat('0.000');
note(model,22,'Yellow inputs are a snapshot. Editing them recalculates current picks. A source refresh and refit require rerunning the analysis.');
note(model,23,'Contributions below standardize each raw input, multiply by its fitted coefficient, then sum with the intercept.');
note(model,47,'Raw pregame inputs. Rates are fractions unless their definition states percentage points.');note(model,66,'Each standardized input contributes to home-team log odds. These are predictive associations, not causal effects.');
const method=[
 'Data: regular seasons 2023–2026. 2022 warms prior team/QB statistics. The canceled 2022 BUF–CIN game is excluded.',
 'Each historical week uses only earlier weeks for efficiency, QB performance and snap shares. Final weekly injury reports are assumed available.',
 'Prior team season: last 12 games at 45% weight. Current season: full weight. Rates have a 100-play neutral prior.',
 'QB sample: current and two prior seasons, decayed 0.65 per year. QB EPA adds 150 neutral-prior dropbacks. CPOE adds 100.',
 'Unavailable player load sums prior four TEAM-game snap shares, including zero participation. QB injuries enter through the projected starter.',
 'Out, doubtful, IR and suspension count as unavailable. Questionable is a separate learned feature. No arbitrary 50% availability assumption.',
 'The expanded feature family follows the requested scope. Penalties 3, 15 and 60 were compared on rolling 2025 Brier scores.',
 'The simpler QB/efficiency family did slightly better in 2025. This does not establish that every added feature improves predictions.',
 '2026 comparisons are exploratory retrospective checks, not a prospectively locked trial. Forecasts are conditional on a decisive result.',
 ...data.limitations,
 'Data quality: all 136 current-season scores reconcile to ESPN. Player ID mapping covers '+(100*data.quality.unique_player_map_rate).toFixed(2)+'% of snap rows.',
 'Four conflicting injury rows (two 2024 player/week keys) were excluded. Source records without recent snaps are not treated as proven healthy.',
 'Official team staff pages supply HC/OC/DC names. Coaching tab has per-team links. Carolina changed DC on October 30.',
 'The original Elo formulas and 272-game schedule remain available in Games and Teams. Model 2 historical probabilities are appended to Games.',
 ...data.sources.map(s=>s.name+': '+s.url)
];method.forEach((v,i)=>note(model,85+i,v));
model.freezePanes.freezeRows(7);
// Extend the existing game table with the richer model's historical and current predictions.
header(games,6,['Model 2 home %','Model 2 pick','Model 2 correct','Model 2 Brier','Model 2 log loss'],26);
games.getRange(`AA7:AE${end}`).format.font={name:'Arial',size:10,color:'#183044'};games.getRange(`AA7:AE${end}`).format.columnWidth=16;
const aa=[],ab=[],ac=[],ad=[],ae=[];
for(let i=0;i<base.games.length;i++){
 const g=base.games[i],r=i+7,t=testById[g.id],f=forecastById[g.id];
 if(f)games.getRange(`AA${r}`).formulas=[[`='Model 2'!E${f.modelRow}`]];else games.getRange(`AA${r}`).values=[[t?t.p:null]];
 ab.push([`=IF(ISNUMBER(AA${r}),IF(AA${r}>=0.5,F${r},E${r}),"")`]);
 ac.push([`=IF(AND(ISNUMBER(AA${r}),J${r}="Final",K${r}<>"Tie"),IF(AB${r}=K${r},1,0),"")`]);
 ad.push([`=IF(ISNUMBER(AC${r}),(AA${r}-IF(K${r}=F${r},1,0))^2,"")`]);
 ae.push([`=IF(ISNUMBER(AC${r}),-LN(IF(K${r}=F${r},AA${r},1-AA${r})),"")`]);
}
games.getRange(`AB7:AB${end}`).formulas=ab;games.getRange(`AC7:AC${end}`).formulas=ac;games.getRange(`AD7:AD${end}`).formulas=ad;games.getRange(`AE7:AE${end}`).formulas=ae;
games.getRange(`AA7:AA${end}`).setNumberFormat('0.0%');games.getRange(`AD7:AE${end}`).setNumberFormat('0.000');
games.tables.items[0].delete();table(games,`A6:AE${end}`,'SeasonGames');
// Replace the main picks with the new model, retaining automatic result scoring.
picks.getRange('J1:Q28').clear({applyTo:'all'});picks.getRange('A22:H28').clear({applyTo:'contents'});
picks.getRange('A2').values=[['NFL Week 10 predictions — Model 2']];
note(picks,4,'Sunday, November 15 and Monday, November 16, 2026. Eastern kickoff times. Data snapshot: November 10.');
note(picks,5,'Updated for projected QBs, injuries, offense, defense, rest, coaching changes and forecast weather. Estimates depend on current inputs.');
header(picks,7,['Date (ET)','Kickoff (ET)','Away','Home','Pick','Estimated win %','Actual winner','Pick result']);
header(picks,7,['Away projected QB','Home projected QB','Review before kickoff'],9);
picks.getRange('J1:K28').format.columnWidth=23;picks.getRange('L1:L28').format.columnWidth=33;picks.getRange('J8:L20').format.font={name:'Arial',size:10,color:'#183044'};
for(let i=0;i<data.forecast.length;i++){
 const g=data.forecast[i],r=i+8,source=rowById[g.espn_id];const flags=[];
 if(g.away_qb.dropbacks<30||g.home_qb.dropbacks<30)flags.push('QB NFL sample <30');
 if(data.injuries.some(x=>[g.away_qb.id,g.home_qb.id].includes(x.gsis_id)&&x.status==='Questionable'))flags.push('QB questionable');
 if(g.pick_probability<.55)flags.push('Near 50/50');
 picks.getRange(`A${r}:D${r}`).values=[[excelDate(g.date),time(g.kickoff),g.away,g.home]];
 picks.getRange(`E${r}:H${r}`).formulas=[[
  `=IF('Model 2'!E${i+8}>=0.5,D${r},C${r})`,`=MAX('Model 2'!E${i+8},1-'Model 2'!E${i+8})`,
  `=IF('Games'!J${source}="Final",'Games'!K${source},"Pending")`,`=IF(G${r}="Pending","Pending",IF(G${r}="Tie","Tie",IF(G${r}=E${r},"Correct","Incorrect")))`]];
 picks.getRange(`J${r}:L${r}`).values=[[g.away_qb.name,g.home_qb.name,flags.join('; ')||'Final reports pending']];
}
picks.getRange('F8:F20').setNumberFormat('0%');picks.getRange('J8:L20').format.wrapText=true;picks.getRange('A8:L20').format.rowHeight=31;
note(picks,22,'Projected starters and Tuesday injury reports may change. Retractable roofs are assumed closed. NE–DET is neutral in Munich.');
note(picks,24,'See Performance for historical checks, Matchup factors for weather and scenarios, and QB analysis / Injuries / Coaching for detail.');
note(picks,26,'Scenario ranges are sensitivity checks, not confidence intervals. Probabilities do not explicitly model ties.');
// Expand team metrics without altering the original standings or Elo columns.
const tm=Object.fromEntries(data.team_metrics.map(t=>[t.team,t]));
header(teams,6,['2026 off. EPA/play','2026 def. EPA allowed','2026 success %','Opp. success %','Model off. EPA','Model def. EPA','Pass EPA allowed','Rush EPA allowed','Def. sack rate','QB-hit rate proxy','Explosive allowed','Pass over expected','Projected QB'],12);
for(let i=0;i<base.teams.length;i++){
 const t=tm[base.teams[i].code];teams.getRange(`M${i+7}:Y${i+7}`).values=[[t.season_off_epa,t.season_def_epa,t.season_success,t.season_def_success,t.off_epa,t.def_epa,t.def_pass_epa,t.def_rush_epa,t.def_sack_rate,t.pressure_proxy,t.def_explosive,t.proe,t.projected_qb]];
}
teams.getRange('M7:X38').setNumberFormat('0.000');teams.getRange('O7:P38').setNumberFormat('0.0%');teams.getRange('U7:W38').setNumberFormat('0.0%');teams.getRange('M6:X38').format.columnWidth=18;teams.getRange('Y6:Y38').format.columnWidth=24;teams.getRange('M7:Y38').format.font={name:'Arial',size:10,color:'#183044'};
teams.tables.items[0].delete();table(teams,'A6:Y38','TeamResults');
// Performance: compare models on the same 135 decisive games.
perf.getRange('A2').values=[['Prediction model performance']];perf.getRange('A5:F16').clear({applyTo:'contents'});
note(perf,4,'2026 rolling retrospective comparison. Recorded starting lineups and observed weather are assumed known. These are exploratory results.');
const pm=[['Model 2 decisive games',`=COUNT(${gr('AC')})`],['Model 2 correct picks',`=SUM(${gr('AC')})`],['Model 2 accuracy','=B6/B5'],['Model 2 Brier score',`=AVERAGE(${gr('AD')})`],['Model 2 log loss',`=AVERAGE(${gr('AE')})`],['Original Elo accuracy',`=SUM(${gr('P')})/COUNT(${gr('P')})`],['Original Elo Brier score',`=AVERAGE(${gr('Q')})`],['QB / efficiency model accuracy',data.evaluations[0].accuracy],['QB / efficiency Brier score',data.evaluations[0].brier],['2025 expanded-model accuracy',data.selected.accuracy],['2025 expanded-model Brier',data.selected.brier],['Selected regularization penalty',data.selected.alpha]];
pm.forEach(([label,value],i)=>{let r=i+5;perf.getRange(`A${r}`).values=[[label]];if(typeof value==='string')perf.getRange(`B${r}`).formulas=[[value]];else perf.getRange(`B${r}`).values=[[value]];});
perf.getRange('B5:B16').setNumberFormat('0.000');for(const r of [5,6,16])perf.getRange(`B${r}`).setNumberFormat('0');for(const r of [7,10,12,14])perf.getRange(`B${r}`).setNumberFormat('0.0%');
note(perf,18,'The simpler model did slightly better in 2025. Added features have not demonstrated a consistent advantage across seasons.');
perf.getRange('A21').values=[['Original Elo defaults (benchmark)']];
note(perf,28,'Weekly comparison scores the same decisive games, including neutral venues. Ties are excluded.');
header(perf,30,['Week','Games scored','Model 2 correct','Elo correct','Model 2 accuracy','Elo accuracy']);
for(let week=1;week<=9;week++){
 const r=week+30;perf.getRange(`A${r}`).values=[[week]];perf.getRange(`B${r}:F${r}`).formulas=[[
 `=COUNTIFS(${gr('B')},A${r},${gr('J')},"Final",${gr('K')},"<>Tie")`,
 `=SUMIFS(${gr('AC')},${gr('B')},A${r})`,`=SUMIFS(${gr('P')},${gr('B')},A${r})`,`=C${r}/B${r}`,`=D${r}/B${r}`]];
}
const chart=perf.charts.items[0];chart.setData([perf.getRange('A30:A39'),perf.getRange('E30:E39'),perf.getRange('F30:F39')]);chart.title='Weekly winner accuracy (same games)';chart.series.items[0].line={fill:navy,style:'solid',width:2};chart.series.items[1].line={fill:'#8594A3',style:'dashed',width:2};
header(perf,26,['Model','Games','Correct','Accuracy','Brier','Log loss'],7);perf.getRange('H27:M30').values=data.evaluations.map(e=>[e.model==='Weather interactions'?'Model 2 (expanded)':e.model==='Injuries + coaching + rest'?'Without weather':e.model,e.games,e.correct,e.accuracy,e.brier,e.logloss]);perf.getRange('H26:H30').format.columnWidth=28;perf.getRange('K27:K30').setNumberFormat('0.0%');perf.getRange('L27:M30').setNumberFormat('0.000');
perf.getRange('A42:P55').clear({applyTo:'contents'});
data.limitations.forEach((v,i)=>note(perf,42+i,v));
// QB statistical detail for every team, including explicit blanks for no NFL sample.
setup(qbs,'Quarterback analysis','N',43,[9,25,13,16,16,16,16,15,15,16,26,23,24,25]);
note(qbs,4,'Projected starters as of November 10. Model sample uses current season and two prior seasons. EPA/CPOE are shrunk toward zero.');
note(qbs,5,'Blank season efficiency means no observed 2026 sample. Model priors for inexperienced QBs are estimates, not measured performance.');
header(qbs,7,['Team','Projected QB','2026 dropbacks','2026 QB EPA/DB','2026 CPOE (pp)','Model QB EPA/DB','Model CPOE (pp)','Model sack rate','Model INT rate','Prior dropbacks','Availability / sample','GSIS ID','Depth chart','Source']);
const depthSources=JSON.parse(await fs.readFile(new URL('collection.json',import.meta.url),'utf8'));
data.qb_metrics.forEach((q,i)=>{const status=data.injuries.find(x=>x.team===q.team&&x.gsis_id===q.id)?.status;const source=depthSources.find(x=>x.file===`depth_${q.team}.json`)?.url;const flags=[status||'Projected starter',q.dropbacks<30?'NFL sample <30':null].filter(Boolean).join('; ');
 qbs.getRange(`A${i+8}:N${i+8}`).values=[[q.team,q.name,q.season_dropbacks,q.season_epa,q.season_cpoe,q.epa,q.cpoe,q.sack_rate,q.int_rate,q.dropbacks,flags,q.id,source,'nflverse play-by-play and ESPN']];});
qbs.getRange('D8:G39').setNumberFormat('0.000');qbs.getRange('H8:I39').setNumberFormat('0.0%');qbs.getRange('K8:K39').format.wrapText=true;qbs.getRange('A8:N39').format.rowHeight=31;table(qbs,'A7:N39','QuarterbackMetrics');qbs.freezePanes.freezeRows(7);qbs.freezePanes.freezeColumns(2);
// Forecast weather, injury workload and scenario analysis share one matchup worksheet.
setup(factors,'Matchup factors and sensitivity','J',110,[21,18,17,17,16,18,35,25,24,25]);
note(factors,4,'City-level forecast at the nearest kickoff hour. Outdoor weather is ignored when a roof is assumed closed.');
note(factors,5,'Tuesday statuses are provisional. Scenarios change one assumption at a time and are not prediction intervals.');
header(factors,7,['Matchup','Temp (F)','Wind (mph)','Gust (mph)','Precip. chance','Precip. (in)','Roof / venue','Weather check','Forecast valid UTC','Forecast source']);
data.forecast.forEach((g,i)=>{const w=g.weather;factors.getRange(`A${i+8}:J${i+8}`).values=[[g.away+' @ '+g.home,w.temperature_f,w.wind_mph,w.gust_mph,w.precip_probability,w.precip_in,g.roof,w.gust_mph<w.wind_mph?'Gust below wind: verify':'Forecast available',w.valid_utc,w.source]];});
factors.getRange('B8:D20').setNumberFormat('0.0');factors.getRange('E8:E20').setNumberFormat('0%');factors.getRange('F8:F20').setNumberFormat('0.00');factors.getRange('G8:H20').format.wrapText=true;factors.getRange('A8:J20').format.rowHeight=32;table(factors,'A7:J20','KickoffWeather');
note(factors,22,'Only sustained wind and cold interactions enter the model. Gust inconsistencies are flagged and do not affect a fitted input.');
note(factors,24,'Unavailable load sums recent snap shares. A value of 1 equals one full-snap player. Long-term IR absences with no recent snaps add zero.');
header(factors,26,['Matchup','Away OL load','Home OL load','Away skill load','Home skill load','Away def. load','Home def. load','Away Q load','Home Q load']);
data.forecast.forEach((g,i)=>{const a=g.away_injury,h=g.home_injury;factors.getRange(`A${i+27}:I${i+27}`).values=[[g.away+' @ '+g.home,a.ol_out,h.ol_out,a.skill_out,h.skill_out,a.def_out,h.def_out,a.questionable,h.questionable]];});factors.getRange('B27:I39').setNumberFormat('0.00');
header(factors,43,['Matchup','Assumption','Home team','Home win estimate','Baseline home %','Change (pp)']);
let sr=44;for(const g of data.forecast)for(const v of g.scenarios){factors.getRange(`A${sr}:C${sr}`).values=[[g.away+' @ '+g.home,v.scenario,g.home]];factors.getRange(`D${sr}:E${sr}`).values=[[v.home_probability,g.home_probability]];factors.getRange(`F${sr}`).formulas=[[`=100*(D${sr}-E${sr})`]];sr++;}
factors.getRange(`B44:B${sr-1}`).format.columnWidth=31;factors.getRange(`D44:E${sr-1}`).setNumberFormat('0.0%');factors.getRange(`F44:F${sr-1}`).setNumberFormat('0.0');table(factors,`A43:F${sr-1}`,'ScenarioEstimates');
// Current injury register, ordered by recent participation rather than celebrity/name.
const injuryRows=[...data.injuries].sort((a,b)=>(b.prior_off_snap_share+b.prior_def_snap_share)-(a.prior_off_snap_share+a.prior_def_snap_share)||a.team.localeCompare(b.team));
setup(inj,'Current injury register','J',injuryRows.length+9,[9,26,12,21,21,19,19,25,26,25]);
note(inj,4,'ESPN game summaries and depth charts, retrieved November 10. These are current reported statuses, not final game-day inactives.');
note(inj,5,'Prior snap share averages the last four TEAM games, including zero participation. Blank injury detail remains unknown.');
header(inj,7,['Team','Player','Position','Reported status','Injury detail','Prior off. snap share','Prior def. snap share','Report timestamp UTC','GSIS ID','Source']);
inj.getRange(`A8:J${injuryRows.length+7}`).values=injuryRows.map(x=>[x.team,x.player,x.position,x.status,x.injury??null,x.prior_off_snap_share,x.prior_def_snap_share,x.updated,x.gsis_id??null,x.source]);inj.getRange(`F8:G${injuryRows.length+7}`).setNumberFormat('0.0%');table(inj,`A7:J${injuryRows.length+7}`,'ReportedInjuries');inj.freezePanes.freezeRows(7);inj.freezePanes.freezeColumns(2);
setup(coaches,'Coaching staff and team tendencies','J',43,[9,25,26,28,17,18,17,16,38,30]);
note(coaches,4,'Current HC, OC and DC from official team pages. These team statistics measure performance under the staff, not causal coaching quality.');
note(coaches,5,'2026 averages can span staff changes. New-HC status enters the model. Coordinator identity is context without an invented rating.');
header(coaches,7,['Team','Head coach','Offensive coordinator','Defensive coordinator','2026 off. EPA/play','2026 def. EPA allowed','Pass over expected (pp)','Games observed','Staff change note','Official staff source']);
data.staff.forEach((c,i)=>{const t=tm[c.team];coaches.getRange(`A${i+8}:J${i+8}`).values=[[c.team,c.head_coach,c.offensive_coordinator,c.defensive_coordinator,t.season_off_epa,t.season_def_epa,t.season_proe,t.games,c.change_note??null,c.coordinator_update_source??c.source]];});coaches.getRange('E8:G39').setNumberFormat('0.000');coaches.getRange('B8:D39').format.wrapText=true;coaches.getRange('I8:I39').format.wrapText=true;coaches.getRange('A8:J39').format.rowHeight=34;table(coaches,'A7:J39','CoachingStaffs');coaches.freezePanes.freezeRows(7);coaches.freezePanes.freezeColumns(1);
wb.recalculate();
for(let i=0;i<data.forecast.length;i++){
 const g=data.forecast[i],p=model.getRange(`E${i+8}`).values[0][0];if(Math.abs(p-g.home_probability)>1e-10)throw Error('Model equation mismatch '+g.espn_id);
 const v=picks.getRange(`E${i+8}:F${i+8}`).values[0];if(v[0]!==g.pick||Math.abs(v[1]-g.pick_probability)>1e-10)throw Error('Prediction mismatch');
}
for(const [cell,value]of [['B5',135],['B6',selectedEval.correct],['B7',selectedEval.accuracy],['B8',selectedEval.brier],['B9',selectedEval.logloss]])if(Math.abs(perf.getRange(cell).values[0][0]-value)>1e-10)throw Error('Performance mismatch '+cell);
for(const [i,g]of data.forecast.entries()){const cell=model.getRange(`C${i+51}`),old=cell.values[0][0];cell.values=[[old===0?1:0]];const changed=picks.getRange(`F${i+8}`).values[0][0];cell.values=[[old]];if(changed===g.pick_probability)throw Error('Input propagation did not change forecast');break;}
const first=data.forecast[0],gameRow=rowById[first.espn_id];games.getRange(`G${gameRow}:H${gameRow}`).values=[[0,3]];if(picks.getRange('G8').values[0][0]!==first.home)throw Error('Actual score propagation failed');games.getRange(`G${gameRow}:H${gameRow}`).values=[[null,null]];wb.recalculate();
if(perf.getRange('B5').values[0][0]!==135)throw Error('Restoration failed');
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:15},summary:'Final formula error scan',maxChars:1200})).ndjson);
const previews=[['Predictions','A1:H26','picks-v2'],['Teams','M5:Y18','teams-v2'],['Games','AA5:AE19','games-v2'],['Performance','A1:P39','performance-v2'],['Model 2','A1:E23','model-v2'],['QB analysis','A1:K18','qbs-v2'],['Matchup factors','A1:I22','weather-v2'],['Injuries','A1:H18','injuries-v2'],['Coaching','A1:I18','coaching-v2']].filter(x=>!process.env.NFL_RENDER_SHEETS||process.env.NFL_RENDER_SHEETS.split(',').includes(x[0]));
for(const [sheet,range,name]of previews){const image=await wb.render({sheetName:sheet,range,scale:1.2,format:'png'});await fs.writeFile(new URL(name+'.png',import.meta.url),new Uint8Array(await image.arrayBuffer()));}
const output=await SpreadsheetFile.exportXlsx(wb);await output.save(path(new URL('../../outputs/nfl-2026/nfl-season-tracker-2026.xlsx',import.meta.url)));
await fs.writeFile(new URL('workbook-validation.json',import.meta.url),JSON.stringify({forecasts:13,backtest:135,correct:selectedEval.correct,brier:selectedEval.brier,inputPropagation:true,scorePropagation:true,worksheets:9,coachingEntries:32,injuries:injuryRows.length},null,2));
console.log('Enhanced workbook exported.');
function letter(i){let s='';for(i++;i>0;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s;}
