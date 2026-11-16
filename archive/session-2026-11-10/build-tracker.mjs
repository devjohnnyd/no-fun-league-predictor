import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
process.on('uncaughtException',error=>{console.error(error.message);process.exit(1)});
const d=JSON.parse(await fs.readFile(new URL('analysis.json',import.meta.url),'utf8'));
const wb=Workbook.create();
const picks=wb.worksheets.add('Predictions'),teams=wb.worksheets.add('Teams'),games=wb.worksheets.add('Games'),perf=wb.worksheets.add('Performance');
const out=new URL('../outputs/nfl-2026/',import.meta.url);await fs.mkdir(out,{recursive:true});
const navy='#17324D',muted='#53677B',blue='#E8F0F8';
const end=d.games.length+6, gr=c=>`'Games'!$${c}$7:$${c}$${end}`;
function setup(s,title,lastCol,lastRow,widths){
 s.showGridLines=false;s.getRange(`A1:${lastCol}${lastRow}`).format.font={name:'Arial',size:10,color:'#183044'};
 s.getRange(`A1:${lastCol}${lastRow}`).format.rowHeight=23;
 s.getRange(`A1:${lastCol}${lastRow}`).format.verticalAlignment='center';
 s.getRange('A2').values=[[title]];s.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:navy};
 s.getRange(`A3:${lastCol}3`).format.borders={bottom:{style:'thin',color:'#9CB0C2'}};
 widths.forEach((w,i)=>s.getRangeByIndexes(0,i,lastRow,1).format.columnWidth=w);
}
function hdr(s,row,names){const r=s.getRangeByIndexes(row-1,0,1,names.length);r.values=[names];r.format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true};r.format.rowHeight=34;}
function note(s,row,text){s.getRange(`A${row}`).values=[[text]];s.getRange(`A${row}`).format.font={name:'Arial',size:10,color:muted};}
function colForm(s,col,arr,start=7){s.getRange(`${col}${start}:${col}${start+arr.length-1}`).formulas=arr.map(x=>[x]);}
setup(games,'2026 NFL regular-season game tracker','Y',end,[14,7,13,12,9,9,11,11,10,12,10,13,13,14,11,10,11,11,13,13,13,25,24,33,16]);
note(games,4,'Source: ESPN weekly scoreboards. Season 2026, regular season, weeks 1–18. Retrieved '+d.asOf+'.');
note(games,5,'Final scores are inputs. Elo columns recalculate from prior games. Future picks use current ratings. Dates and kickoff times are Eastern.');
hdr(games,6,['Game ID','Week','Date (ET)','Kickoff (ET)','Away','Home','Away score','Home score','Neutral','Status','Winner','Away Elo before','Home Elo before','Home win estimate','Elo pick','Correct (1/0)','Brier score','Log loss','Away Elo after','Home Elo after','Home pick correct','Game source','Kickoff UTC','Venue','Broadcast']);
games.getRange(`A7:Y${end}`).values=d.games.map(g=>[g.id,g.week,excelDate(g.date),parseTime(g.time),g.away,g.home,g.awayScore,g.homeScore,g.neutral?'Yes':'No',null,null,null,null,null,null,null,null,null,null,null,null,g.source,g.kickoff,g.venue,g.broadcast]);
games.getRange(`C7:C${end}`).setNumberFormat('mm/dd/yy');games.getRange(`D7:D${end}`).setNumberFormat('h:mm AM/PM');
games.getRange(`G7:H${end}`).format.fill='#FFF4D1';
games.getRange(`L7:N${end}`).setNumberFormat('0.0');games.getRange(`N7:N${end}`).setNumberFormat('0.0%');games.getRange(`Q7:R${end}`).setNumberFormat('0.000');games.getRange(`S7:T${end}`).setNumberFormat('0.0');
const prev={},f={J:[],K:[],L:[],M:[],N:[],O:[],P:[],Q:[],R:[],S:[],T:[],U:[]},gameRows={};
for(let i=0;i<d.games.length;i++){
 const g=d.games[i],r=i+7;gameRows[g.id]=r;
 f.J.push(`=IF(AND(ISNUMBER(G${r}),ISNUMBER(H${r})),"Final","Scheduled")`);
 f.K.push(`=IF(J${r}<>"Final","",IF(G${r}=H${r},"Tie",IF(G${r}>H${r},E${r},F${r})))`);
 f.L.push(prev[g.away]?`=${prev[g.away]}`:"='Performance'!$B$23");f.M.push(prev[g.home]?`=${prev[g.home]}`:"='Performance'!$B$23");
 f.N.push(`=1/(1+10^((L${r}-M${r}-IF(I${r}="Yes",0,'Performance'!$B$25))/'Performance'!$B$26))`);
 f.O.push(`=IF(N${r}>=0.5,F${r},E${r})`);
 f.P.push(`=IF(OR(J${r}<>"Final",K${r}="Tie"),"",IF(O${r}=K${r},1,0))`);
 f.Q.push(`=IF(ISNUMBER(P${r}),(N${r}-IF(K${r}=F${r},1,0))^2,"")`);
 f.R.push(`=IF(ISNUMBER(P${r}),-LN(IF(K${r}=F${r},N${r},1-N${r})),"")`);
 f.S.push(`=L${r}-IF(J${r}="Final",'Performance'!$B$24*(IF(K${r}="Tie",0.5,IF(K${r}=F${r},1,0))-N${r}),0)`);
 f.T.push(`=M${r}+IF(J${r}="Final",'Performance'!$B$24*(IF(K${r}="Tie",0.5,IF(K${r}=F${r},1,0))-N${r}),0)`);
 f.U.push(`=IF(OR(J${r}<>"Final",K${r}="Tie",I${r}="Yes"),"",IF(K${r}=F${r},1,0))`);
 prev[g.away]=`'Games'!S${r}`;prev[g.home]=`'Games'!T${r}`;
}
for(const [col,arr]of Object.entries(f))colForm(games,col,arr);
games.tables.add(`A6:Y${end}`,true,'SeasonGames');games.freezePanes.freezeRows(6);games.freezePanes.freezeColumns(6);
setup(teams,'Team results and current ratings','L',40,[9,30,9,8,8,8,13,13,12,13,13,13]);
note(teams,4,'Regular-season results through November 9, 2026. Sorted by the November 10 Elo rating.');
hdr(teams,6,['Team','Name','Played','Wins','Losses','Ties','Points for','Points against','Point diff.','Scored/game','Allowed/game','Elo']);
teams.getRange('A7:B38').values=d.teams.map(t=>[t.code,t.name]);
const tf={C:[],D:[],E:[],F:[],G:[],H:[],I:[],J:[],K:[],L:[]};
for(let i=0;i<d.teams.length;i++){const r=i+7,t=d.teams[i];
 tf.C.push(`=COUNTIFS(${gr('E')},A${r},${gr('J')},"Final")+COUNTIFS(${gr('F')},A${r},${gr('J')},"Final")`);
 tf.D.push(`=COUNTIFS(${gr('K')},A${r})`);
 tf.F.push(`=COUNTIFS(${gr('E')},A${r},${gr('K')},"Tie")+COUNTIFS(${gr('F')},A${r},${gr('K')},"Tie")`);
 tf.E.push(`=C${r}-D${r}-F${r}`);
 tf.G.push(`=SUMIFS(${gr('G')},${gr('E')},A${r})+SUMIFS(${gr('H')},${gr('F')},A${r})`);
 tf.H.push(`=SUMIFS(${gr('H')},${gr('E')},A${r})+SUMIFS(${gr('G')},${gr('F')},A${r})`);
 tf.I.push(`=G${r}-H${r}`);tf.J.push(`=IF(C${r}=0,"",G${r}/C${r})`);tf.K.push(`=IF(C${r}=0,"",H${r}/C${r})`);tf.L.push('='+prev[t.code]);
}
for(const [col,arr]of Object.entries(tf))colForm(teams,col,arr);
teams.getRange('J7:L38').setNumberFormat('0.0');teams.tables.add('A6:L38',true,'TeamResults');teams.freezePanes.freezeRows(6);teams.freezePanes.freezeColumns(2);
setup(perf,'Model performance and assumptions','P',53,[37,16,15,14,14,14,3,13,13,13,13,13,13,13,13,13]);
note(perf,4,'Historical reconstruction using only previous weeks. This is an exploratory baseline, without a separate held-out test.');
const metrics=[['Completed games',`=COUNTIFS(${gr('J')},"Final")`],['Decisive games scored',`=COUNT(${gr('P')})`],['Correct Elo picks',`=SUM(${gr('P')})`],['Elo winner accuracy','=B7/B6'],['Elo Brier score',`=AVERAGE(${gr('Q')})`],['50/50 Brier benchmark','=0.25'],['Elo log loss',`=AVERAGE(${gr('R')})`],['50/50 log loss','=LN(2)'],['Tied games excluded',`=COUNTIFS(${gr('K')},"Tie")`],['Non-neutral decisive games',`=COUNT(${gr('U')})`],['Elo accuracy, non-neutral',`=SUMIFS(${gr('P')},${gr('I')},"No")/B14`],['Home-pick accuracy, non-neutral',`=SUM(${gr('U')})/B14`]];
for(let i=0;i<metrics.length;i++){let r=i+5;perf.getRange(`A${r}`).values=[[metrics[i][0]]];perf.getRange(`B${r}`).formulas=[[metrics[i][1]]];}
perf.getRange('B8').setNumberFormat('0.0%');perf.getRange('B9:B12').setNumberFormat('0.000');perf.getRange('B15:B16').setNumberFormat('0.0%');
note(perf,18,'Lower Brier scores and log loss are better. Small differences here do not establish a reliable predictive advantage.');
perf.getRange('A21').values=[['Elo v1 defaults']];perf.getRange('A21').format.font.bold=true;
perf.getRange('A23:B26').values=[['Initial rating',1500],['K update factor',32],['Home advantage (Elo)',55],['Logistic scale',400]];
note(perf,28,'Weekly comparison excludes ties and neutral-site games so both methods score the same games.');
hdr(perf,30,['Week','Games scored','Elo correct','Home correct','Elo accuracy','Home accuracy']);
for(let w=1;w<=9;w++){const r=w+30;perf.getRange(`A${r}`).values=[[w]];perf.getRange(`B${r}:F${r}`).formulas=[[
 `=COUNTIFS(${gr('B')},A${r},${gr('J')},"Final",${gr('I')},"No",${gr('K')},"<>Tie")`,
 `=SUMIFS(${gr('P')},${gr('B')},A${r},${gr('I')},"No")`,
 `=SUMIFS(${gr('U')},${gr('B')},A${r})`,`=C${r}/B${r}`,`=D${r}/B${r}`]];}
perf.getRange('E31:F39').setNumberFormat('0.0%');
const chart=perf.charts.add('line',[perf.getRange('A30:A39'),perf.getRange('E30:E39'),perf.getRange('F30:F39')]);chart.title='Weekly winner accuracy (same games)';chart.setPosition('H6','P22');chart.titleTextStyle.typeface='Arial';chart.titleTextStyle.fontSize=13;chart.legend={position:'bottom',textStyle:{typeface:'Arial'}};chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial'}};chart.yAxis={numberFormatCode:'0%',numberFormatSourceLinked:false,textStyle:{typeface:'Arial'}};chart.series.items[0].line={fill:navy,style:'solid',width:2};chart.series.items[1].line={fill:'#8594A3',style:'dashed',width:2};
const rules=[
 'All teams start equal. Fixed defaults are not tuned or calibrated to this season.',
 'Home win estimate = 1 / (1 + 10 ^ ((away Elo − home Elo − home advantage) / 400)).',
 'After each game: home Elo changes by 32 × (actual home result − estimated home result). Away changes by the opposite amount.',
 'Actual result is 1 for a win, 0 for a loss and 0.5 for a tie. Neutral-site games get no home advantage.',
 'Ties update ratings but are excluded from winner accuracy, Brier score and log loss. Forecasts do not explicitly model ties.',
 'No injuries, quarterback availability, weather, rest, market odds or previous seasons enter this version.',
 'Predictions preserves the November 10 rating snapshot. Changing Games updates Teams and historical performance, not those saved inputs.',
 'To refresh: ask to refresh this tracker. Retain the original prediction rows and score them against final outcomes. No refresh is scheduled.',
 'Coverage checks: 272 unique games, 32 teams, 17 games/team. Total points for equals total points against.',
 'Official samples checked: NE 10–SEA 13 and SF 27–LAR 7 (Week 1). BUF 23–MIN 6 (Week 9 official gamebook).',
 'Official results: https://www.nfl.com/schedules/2026/by-week/week-9',
 'Official gamebook: https://static.www.nfl.com/gamecenter/ab5825a7-4feb-11f1-abca-2c54536568a9.pdf'];
rules.forEach((x,i)=>note(perf,42+i,x));
setup(picks,'NFL Week 10 predictions','O',28,[14,12,10,10,12,18,15,14,3,14,14,14,14,14,15]);picks.tabColor=navy;
note(picks,4,'Sunday, November 15 and Monday, November 16, 2026. All kickoff times are Eastern. Snapshot: November 10.');
note(picks,5,'Preliminary results-only estimates. Probabilities are uncalibrated. Injuries, quarterback changes and weather are excluded.');
hdr(picks,7,['Date (ET)','Kickoff (ET)','Away','Home','Pick','Estimated win %','Actual winner','Pick result']);
picks.getRange('J7:O7').values=[['Away Elo saved','Home Elo saved','Home edge saved','Scale saved','Home estimate','Game ID']];picks.getRange('J7:O7').format={fill:blue,font:{bold:true},wrapText:true};
for(let i=0;i<d.forecasts.length;i++){
 const g=d.forecasts[i],r=i+8,src=gameRows[g.id];
 picks.getRange(`A${r}:D${r}`).values=[[excelDate(g.date),parseTime(g.time),g.away,g.home]];
 picks.getRange(`J${r}:M${r}`).values=[[g.awayElo,g.homeElo,g.neutral?0:55,400]];picks.getRange(`O${r}`).values=[[g.id]];
 picks.getRange(`N${r}`).formulas=[[`=1/(1+10^((J${r}-K${r}-L${r})/M${r}))`]];
 picks.getRange(`E${r}:H${r}`).formulas=[[
 `=IF(N${r}>=0.5,D${r},C${r})`,`=MAX(N${r},1-N${r})`,
 `=IF('Games'!J${src}="Final",'Games'!K${src},"Pending")`,
 `=IF(G${r}="Pending","Pending",IF(G${r}="Tie","Tie",IF(G${r}=E${r},"Correct","Incorrect")))`]];
}
picks.getRange('A8:A20').setNumberFormat('ddd mm/dd');picks.getRange('B8:B20').setNumberFormat('h:mm AM/PM');picks.getRange('F8:F20').setNumberFormat('0%');picks.getRange('J8:M20').setNumberFormat('0.0');picks.getRange('N8:N20').setNumberFormat('0.0%');picks.getRange('F8:F20').format.font.bold=true;
picks.tables.add('A7:H20',true,'SavedPredictions');
note(picks,22,'NE–DET is a neutral-site game in Munich. Thursday’s game is tracked in Games but is outside the requested prediction slate.');
note(picks,24,'Historical Elo accuracy: 73 / 135 decisive games (54.1%). These picks have not yet been tested on future games.');
note(picks,26,'For the next update, keep this snapshot and ask to refresh the tracker after the games finish.');
wb.recalculate();
const expected=[['Performance','B5',136],['Performance','B6',135],['Performance','B7',73],['Performance','B8',d.metrics.accuracy],['Performance','B9',d.metrics.brier],['Performance','B14',128],['Performance','B15',70/128],['Performance','B16',66/128],['Teams','L7',d.teams[0].elo],['Predictions','F8',d.forecasts[0].pickProbability]];
for(const [sheet,cell,value]of expected){const actual=wb.worksheets.getItem(sheet).getRange(cell).values[0][0];if(typeof actual!=='number'||Math.abs(actual-value)>1e-8)throw Error(`${sheet}!${cell}: ${actual} != ${value}`);}
for(let w=1;w<=9;w++){
 const subset=d.games.filter(g=>g.week===w&&g.correct!==null&&g.status==='Final'&&!g.neutral);
 const actual=perf.getRange(`B${w+30}:F${w+30}`).values[0];
 const expectedWeekly=[subset.length,subset.reduce((s,g)=>s+g.correct,0),subset.reduce((s,g)=>s+g.homeCorrect,0)];
 for(let i=0;i<3;i++)if(actual[i]!==expectedWeekly[i])throw Error('Weekly backtest mismatch '+w);
}
// Verify every formula-derived pregame rating and saved forecast against the independent analysis.
for(let i=0;i<d.games.length;i++){const g=d.games[i];if(g.status==='Final'){const v=games.getRange(`L${i+7}:N${i+7}`).values[0];for(const [actual,expect]of [[v[0],g.awayEloBefore],[v[1],g.homeEloBefore],[v[2],g.homeProb]])if(Math.abs(actual-expect)>1e-8)throw Error('Elo formula mismatch '+g.id);}}
for(let i=0;i<d.forecasts.length;i++){const g=d.forecasts[i],v=picks.getRange(`E${i+8}:F${i+8}`).values[0];if(v[0]!==g.pick||Math.abs(v[1]-g.pickProbability)>1e-8)throw Error('Forecast mismatch');}
// A future score must update the actual result while leaving the saved forecast unchanged.
const testGame=d.forecasts[0],tr=gameRows[testGame.id],before=picks.getRange('E8:F8').values;
games.getRange(`G${tr}:H${tr}`).values=[[0,3]];wb.recalculate();
if(picks.getRange('G8').values[0][0]!==testGame.home||JSON.stringify(before)!==JSON.stringify(picks.getRange('E8:F8').values))throw Error('Saved forecast/score update failed');
games.getRange(`G${tr}:H${tr}`).values=[[null,null]];wb.recalculate();
if(picks.getRange('G8').values[0][0]!=='Pending'||perf.getRange('B5').values[0][0]!==136)throw Error('Score restoration failed');
console.log((await wb.inspect({kind:'table',range:'Predictions!A7:H11',include:'values,formulas',tableMaxRows:5,tableMaxCols:8,maxChars:2200})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},summary:'Formula error scan',maxChars:1000})).ndjson);
for(const [sheet,range,name]of [['Predictions','A1:H26','predictions'],['Games','A1:K17','games']]){
 const image=await wb.render({sheetName:sheet,range,scale:1.4,format:'png'});await fs.writeFile(new URL(name+'.png',import.meta.url),new Uint8Array(await image.arrayBuffer()));
}
const file=await SpreadsheetFile.exportXlsx(wb);await file.save(new URL('nfl-season-tracker-2026.xlsx',out).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
await fs.writeFile(new URL('validation.json',import.meta.url),JSON.stringify({formulaChecks:expected.length,allHistoricalEloChecked:true,allForecastsChecked:true,scoreUpdateAndRestore:true,charts:perf.charts.items.map(c=>({title:c.title.text,series:c.series.items.map(s=>({formula:s.formula,category:s.categoryFormula}))}))},null,2));
console.log('Exported nfl-season-tracker-2026.xlsx');
function parseTime(t){const m=t.match(/(\d+):(\d+)\s*(AM|PM)/);return ((Number(m[1])%12+(m[3]==='PM'?12:0))*60+Number(m[2]))/1440;}
function excelDate(date){return Date.parse(date+'T00:00:00Z')/86400000+25569;}
