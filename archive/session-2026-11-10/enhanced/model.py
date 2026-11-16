from pathlib import Path
from collections import defaultdict
import json,re,unicodedata,math
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
BASE=json.loads((ROOT.parent/'analysis.json').read_text())
CTX=json.loads((ROOT/'context.json').read_text())
normteam=lambda t:{'LA':'LAR','WAS':'WSH','OAK':'LV','SD':'LAC','STL':'LAR'}.get(t,t)
def namekey(x):return re.sub(r'[^a-z]','',unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower().replace(' jr.','').replace(' iii','').replace(' ii',''))
def native(x):
 if isinstance(x,dict):return {k:native(v) for k,v in x.items()}
 if isinstance(x,list):return [native(v) for v in x]
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,float) and not math.isfinite(x):return None
 return x
schedule=pd.read_csv(ROOT/'raw/schedules.csv',dtype={'espn':'string','home_qb_id':'string','away_qb_id':'string'})
schedule['home_team']=schedule.home_team.map(normteam);schedule['away_team']=schedule.away_team.map(normteam)
schedule=schedule.loc[schedule.game_type.eq('REG') & schedule.season.between(2022,2026)].copy()
schedule['espn']=schedule.espn.str.replace('.0','',regex=False)
schedule=schedule.loc[schedule.season.lt(2026)|schedule.gameday.le('2026-11-10')|schedule.espn.isin([g['id'] for g in BASE['forecasts']])].copy()
schedule=schedule.sort_values(['season','week','gameday','gametime','game_id'])
players=pd.read_csv(ROOT/'raw/players.csv',dtype={'gsis_id':'string','espn_id':'string','pfr_id':'string'})
espnmap={str(r.espn_id).replace('.0',''):r.gsis_id for r in players.itertuples() if pd.notna(r.espn_id) and pd.notna(r.gsis_id)}
pfrmap={r.pfr_id:r.gsis_id for r in players.itertuples() if pd.notna(r.pfr_id) and pd.notna(r.gsis_id)}
namemap={namekey(r.display_name):r.gsis_id for r in players.itertuples() if pd.notna(r.gsis_id)}
qb_names={str(r.gsis_id):r.display_name for r in players.itertuples() if pd.notna(r.gsis_id)}
cols=['game_id','posteam','defteam','season_type','week','play_type','epa','qb_epa','qb_dropback','qb_kneel','qb_spike','qb_scramble','passer_player_id','rusher_player_id','cpoe','sack','interception','qb_hit','yards_gained','pass','rush','pass_oe','season','success','home_score','away_score','home_team','away_team']
team_games={};qb_games=defaultdict(list);source_counts={};pbp_score={}
for year in range(2022,2027):
 cache=ROOT/f'aggregates_{year}.json'
 if cache.exists():
  c=json.loads(cache.read_text());team_games.update(c['team_games']);source_counts[str(year)]=c['counts'];pbp_score.update(c['scores'])
  for k,v in c['qb_games'].items():qb_games[k].extend(v)
  continue
 p=pd.read_csv(ROOT/f'raw/pbp_{year}.csv.gz',usecols=cols,low_memory=False)
 p=p[p.season_type.eq('REG')].copy();p['posteam']=p.posteam.map(normteam);p['defteam']=p.defteam.map(normteam)
 scores=p.groupby('game_id')[['home_score','away_score']].first().to_dict('index');pbp_score.update(scores)
 elig=p.play_type.isin(['pass','run']) & p.qb_kneel.ne(1) & p.qb_spike.ne(1) & p.epa.notna()
 q=p.loc[elig].copy();q['dropbacks']=q.qb_dropback.eq(1).astype(int);q['positive']=q.epa.gt(0).astype(int);q['explosive']=((q['pass'].eq(1)&q.yards_gained.ge(20))|(q['rush'].eq(1)&q.yards_gained.ge(10))).astype(int)
 q['pass_epa']=q.epa.where(q.dropbacks.eq(1),0);q['rush_epa']=q.epa.where(q.dropbacks.eq(0),0)
 metrics={}
 for (gid,team),v in q.groupby(['game_id','posteam']):
  passing=v[v.dropbacks.eq(1)];rushing=v[v.dropbacks.eq(0)]
  metrics[f'{gid}|{team}']={'game_id':gid,'team':team,'season':year,'week':int(v.week.iloc[0]),'plays':len(v),'epa_sum':v.epa.sum(),'success_sum':v.positive.sum(),
    'db':len(passing),'pass_epa_sum':passing.epa.sum(),'runs':len(rushing),'rush_epa_sum':rushing.epa.sum(),'sacks':passing.sack.sum(),'hits':passing.qb_hit.sum(),
    'explosive_sum':v.explosive.sum(),'pass_oe_sum':v.pass_oe.sum(),'pass_oe_n':v.pass_oe.notna().sum()}
 for (gid,team),v in q.groupby(['game_id','defteam']):
  passing=v[v.dropbacks.eq(1)];rushing=v[v.dropbacks.eq(0)];key=f'{gid}|{team}'
  metrics[key].update({'def_plays':len(v),'def_epa_sum':v.epa.sum(),'def_success_sum':v.positive.sum(),'def_db':len(passing),'def_pass_epa_sum':passing.epa.sum(),'def_runs':len(rushing),'def_rush_epa_sum':rushing.epa.sum(),
    'def_sacks':passing.sack.sum(),'def_hits':passing.qb_hit.sum(),'def_explosive_sum':v.explosive.sum()})
 qb=q[q.dropbacks.eq(1)].copy();qb['pid']=qb.passer_player_id.fillna(qb.rusher_player_id);qb['qbepa']=qb.qb_epa.fillna(qb.epa)
 qbs=defaultdict(list)
 for (gid,pid),v in qb.dropna(subset=['pid']).groupby(['game_id','pid']):
  item={'game_id':gid,'season':year,'week':int(v.week.iloc[0]),'db':len(v),'epa_sum':v.qbepa.sum(),'cpoe_sum':v.cpoe.sum(),'cpoe_n':v.cpoe.notna().sum(),'sacks':v.sack.sum(),'ints':v.interception.sum()};qbs[pid].append(item)
 counts={'rows':len(p),'games':p.game_id.nunique(),'offensive_plays':len(q),'qb_dropbacks':len(qb)}
 cache.write_text(json.dumps(native({'team_games':metrics,'qb_games':dict(qbs),'counts':counts,'scores':scores})))
 team_games.update(native(metrics));source_counts[str(year)]=native(counts)
 for k,v in qbs.items():qb_games[k].extend(native(v))
 print('Aggregated',year,counts,flush=True)
current=schedule[schedule.season.eq(2026)&schedule.home_score.notna()]
assert len(current)==136
for g in BASE['games']:
 if g['status']!='Final':continue
 match=current[current.espn.eq(g['id'])]
 assert len(match)==1,(g['id'],'schedule join')
 r=match.iloc[0];assert (r.home_team,r.away_team,int(r.home_score),int(r.away_score))==(g['home'],g['away'],g['homeScore'],g['awayScore'])
 assert pbp_score[r.game_id]['home_score']==g['homeScore'] and pbp_score[r.game_id]['away_score']==g['awayScore']
injury=pd.concat([pd.read_csv(ROOT/f'raw/injuries_{y}.csv') for y in range(2023,2027)],ignore_index=True)
injury['team']=injury.team.map(normteam);injury=injury[injury.game_type.eq('REG')].copy()
ambiguous_injury_rows=int(injury.duplicated(['season','week','team','gsis_id'],False).sum())
injury=injury.loc[~injury.duplicated(['season','week','team','gsis_id'],False)].copy()
snaps=pd.concat([pd.read_csv(ROOT/f'raw/snaps_{y}.csv') for y in range(2023,2027)],ignore_index=True);snaps['team']=snaps.team.map(normteam);snaps=snaps[snaps.game_type.eq('REG')].copy();snaps['pid']=snaps.pfr_player_id.map(pfrmap)
snapmap=defaultdict(list)
for r in snaps.itertuples():
 if pd.notna(r.pid):snapmap[(r.team,r.pid)].append({'season':int(r.season),'week':int(r.week),'off':r.offense_pct,'def':r.defense_pct})
imaps={key:v.to_dict('records') for key,v in injury.groupby(['season','week','team'])}
def before(item,year,week):return (item['season'],item['week'])<(year,week)
def snapweight(team,pid,year,week):
 if not pid:return (0.,0.)
 # Use the team's last four games, including zero participation. A player's
 # last four appearances could be months old and would overstate a long-term IR loss.
 games=[x for x in teamhist.get(team,[]) if before(x,year,week) and x['season']>=year-1][-4:]
 items={(x['season'],x['week']):x for x in snapmap.get((team,pid),[]) if before(x,year,week)}
 return (sum(items.get((g['season'],g['week']),{}).get('off',0.) for g in games)/len(games),sum(items.get((g['season'],g['week']),{}).get('def',0.) for g in games)/len(games)) if games else (0.,0.)
def injuries_for(team,year,week,live=False,allqout=False):
 rows=[i for i in CTX['injuries'] if i['team']==team] if live else imaps.get((year,week,team),[])
 result={'ol_out':0.,'skill_out':0.,'def_out':0.,'questionable':0.,'mapped':0,'active_reports':0}
 for i in rows:
  status=i.get('status') if live else i.get('report_status');position=i.get('position')
  if position=='QB' or status not in ['Out','Doubtful','Questionable','Injured Reserve','IR','Suspension']:continue
  pid=espnmap.get(str(i.get('espn_id'))) if live else i.get('gsis_id')
  if not pid and live:pid=namemap.get(namekey(i.get('player')))
  off,deff=snapweight(team,pid,year,week);result['active_reports']+=1;result['mapped']+=int(off>0 or deff>0)
  if status=='Questionable' and not allqout:result['questionable']+=off+deff;continue
  if position in ['C','G','T','OT','OG','OL']:result['ol_out']+=off
  elif position in ['WR','TE','RB','FB']:result['skill_out']+=off
  else:result['def_out']+=deff
 return result
qb_candidates=defaultdict(list)
for r in CTX['depth']:
 if r['position']=='QB':qb_candidates[r['team']].append(r)
def projected(team,index=0):
 options=[]
 for r in sorted(qb_candidates[team],key=lambda x:x['rank']):
  bad=any(i.get('status') in ['Out','Doubtful','Injured Reserve','IR'] for i in r.get('injuries',[])) or any(i['team']==team and str(i['espn_id'])==str(r['espn_id']) and i['status'] in ['Out','Doubtful','Injured Reserve','IR'] for i in CTX['injuries'])
  if not bad:options.append(r)
 if not options:raise ValueError('No available projected QB '+team)
 r=options[min(index,len(options)-1)];return espnmap.get(str(r['espn_id'])) or namemap.get(namekey(r['name'])) or 'UNKNOWN_'+team,r['name']
teamhist=defaultdict(list)
all_sched=schedule.to_dict('records')
for item in all_sched:
 if pd.isna(item['home_score']):continue
 for side in ['home','away']:
  teamhist[item[side+'_team']].append({'season':int(item['season']),'week':int(item['week']),'game_id':item['game_id'],'coach':item[side+'_coach'],'opponent':item['away_team'] if side=='home' else item['home_team'],'margin':item['home_score']-item['away_score'] if side=='home' else item['away_score']-item['home_score']})
def team_state(team,year,week):
 history=[h for h in teamhist[team] if before(h,year,week) and h['season']>=year-1];current=[h for h in history if h['season']==year]
 prior=[h for h in history if h['season']==year-1];weighted=[]
 for h in prior[-12:]:weighted.append((team_games[f'{h["game_id"]}|{team}'],.45))
 for h in current:weighted.append((team_games[f'{h["game_id"]}|{team}'],1.))
 def rate(num,den,prior_value=0.,prior_n=100):return (sum(v[num]*w for v,w in weighted)+prior_value*prior_n)/(sum(v[den]*w for v,w in weighted)+prior_n)
 recent=[team_games[f'{h["game_id"]}|{team}'] for h in history[-4:]]
 rec_off=sum(x['epa_sum'] for x in recent)/(sum(x['plays'] for x in recent)+100)
 rec_def=sum(x['def_epa_sum'] for x in recent)/(sum(x['def_plays'] for x in recent)+100)
 current_stats=[team_games[f'{h["game_id"]}|{team}'] for h in current]
 def season_rate(num,den):return sum(v[num] for v in current_stats)/sum(v[den] for v in current_stats) if current_stats and sum(v[den] for v in current_stats)>0 else None
 return {'season_off_epa':season_rate('epa_sum','plays'),'season_def_epa':season_rate('def_epa_sum','def_plays'),'season_proe':season_rate('pass_oe_sum','pass_oe_n'),'season_success':season_rate('success_sum','plays'),'season_def_success':season_rate('def_success_sum','def_plays'),
  'off_epa':rate('epa_sum','plays'),'def_epa':rate('def_epa_sum','def_plays'),'pass_epa':rate('pass_epa_sum','db'),'rush_epa':rate('rush_epa_sum','runs'),
  'def_pass_epa':rate('def_pass_epa_sum','def_db'),'def_rush_epa':rate('def_rush_epa_sum','def_runs'),'success':rate('success_sum','plays',.43),
  'def_success':rate('def_success_sum','def_plays',.43),'sack_rate':rate('sacks','db',.065),'pressure_proxy':rate('def_hits','def_db',.15),
  'def_sack_rate':rate('def_sacks','def_db',.065),'explosive':rate('explosive_sum','plays',.10),'def_explosive':rate('def_explosive_sum','def_plays',.10),
  'proe':rate('pass_oe_sum','pass_oe_n'),'pass_rate':rate('db','plays',.60),'recent_net':rec_off-rec_def,'recent_off':rec_off,'recent_def':rec_def,
  'games':len(current),'prior_plays':sum(v['plays']*w for v,w in weighted),'last_coach':history[-1]['coach'] if history else None}
def qb_state(pid,year,week):
 history=[h for h in qb_games.get(pid,[]) if before(h,year,week) and h['season']>=year-2];weighted=[(h,.65**(year-h['season'])) for h in history]
 n=sum(h['db']*w for h,w in weighted);cpoen=sum(h['cpoe_n']*w for h,w in weighted)
 current=[h for h in history if h['season']==year];current_n=sum(h['db'] for h in current);current_cp=sum(h['cpoe_n'] for h in current)
 return {'id':pid,'name':qb_names.get(pid,'No prior NFL sample'),'dropbacks':sum(h['db'] for h in history),'effective_dropbacks':n,'season_dropbacks':current_n,
  'season_epa':sum(h['epa_sum'] for h in current)/current_n if current_n else None,'season_cpoe':sum(h['cpoe_sum'] for h in current)/current_cp if current_cp else None,
  'epa':sum(h['epa_sum']*w for h,w in weighted)/(n+150), 'cpoe':sum(h['cpoe_sum']*w for h,w in weighted)/(cpoen+100),
  'sack_rate':(sum(h['sacks']*w for h,w in weighted)+.065*100)/(n+100),'int_rate':(sum(h['ints']*w for h,w in weighted)+.025*100)/(n+100),
  'experience':np.log1p(n),'new':int(n<30)}
weather_byid={x['game_id']:x for x in CTX['weather']}
RETRACT={'ATL','IND','ARI','DAL'};DOME={'NO','LV','DET','LAC','MIN','HOU'}
def features(g,live=False,backup_side=None,allqout=False,roof_open=False):
 year,week=int(g['season']),int(g['week']);h,a=g['home_team'],g['away_team'];hs,aws=team_state(h,year,week),team_state(a,year,week)
 if live:
  hpid,hn=projected(h,1 if backup_side=='home' else 0);apid,an=projected(a,1 if backup_side=='away' else 0)
 else:hpid,apid=g['home_qb_id'],g['away_qb_id'];hn,an=g['home_qb_name'],g['away_qb_name']
 hq,aq=qb_state(hpid,year,week),qb_state(apid,year,week);hq['name']=hn;aq['name']=an
 hi,ai=injuries_for(h,year,week,live,allqout),injuries_for(a,year,week,live,allqout)
 hist_h=[x for x in teamhist[h] if x['season']==year-1];hist_a=[x for x in teamhist[a] if x['season']==year-1]
 hnew=int(bool(hist_h) and g['home_coach'] not in {x['coach'] for x in hist_h});anew=int(bool(hist_a) and g['away_coach'] not in {x['coach'] for x in hist_a})
 if live:
  w=weather_byid[str(g['espn'])];outdoor=h not in DOME and (h not in RETRACT or roof_open) or g['location']=='Neutral'
  temp=float(w.get('temperature_f',65));wind=float(w.get('wind_mph',0));roof_note='Retractable, assumed closed' if h in RETRACT and not roof_open else 'Indoor' if not outdoor else 'Outdoor'
 else:
  outdoor=g.get('roof') in ['outdoors','open'];temp=float(g['temp']) if pd.notna(g['temp']) else 65.;wind=float(g['wind']) if pd.notna(g['wind']) else 0.;roof_note=g.get('roof')
 passdiff=hs['pass_rate']-aws['pass_rate']
 f={'home_field':0 if g['location']=='Neutral' else 1,'off_epa_diff':hs['off_epa']-aws['off_epa'],'def_epa_diff':hs['def_epa']-aws['def_epa'],
   'recent_net_diff':hs['recent_net']-aws['recent_net'],'qb_epa_diff':hq['epa']-aq['epa'],'qb_cpoe_diff':hq['cpoe']-aq['cpoe'],
   'qb_experience_diff':hq['experience']-aq['experience'],'qb_new_diff':hq['new']-aq['new'],'sack_rate_diff':hs['sack_rate']-aws['sack_rate'],
   'def_sack_diff':hs['def_sack_rate']-aws['def_sack_rate'],'explosive_diff':hs['explosive']-aws['explosive'],
   'rest_diff':max(-7,min(7,g['home_rest']-g['away_rest'])),'new_coach_diff':hnew-anew,'ol_out_diff':hi['ol_out']-ai['ol_out'],
   'skill_out_diff':hi['skill_out']-ai['skill_out'],'def_out_diff':hi['def_out']-ai['def_out'],'questionable_diff':hi['questionable']-ai['questionable'],
   'wind_pass_diff':wind/15*passdiff if outdoor else 0,'cold_pass_diff':max(0,45-temp)/20*passdiff if outdoor else 0}
 return f,{'home_state':hs,'away_state':aws,'home_qb':hq,'away_qb':aq,'home_injury':hi,'away_injury':ai,'roof':roof_note,'temperature':temp,'wind':wind,'outdoor':outdoor,'home_new_coach':hnew,'away_new_coach':anew}
feature_names=['home_field','off_epa_diff','def_epa_diff','recent_net_diff','qb_epa_diff','qb_cpoe_diff','qb_experience_diff','qb_new_diff','sack_rate_diff','def_sack_diff','explosive_diff','rest_diff','new_coach_diff','ol_out_diff','skill_out_diff','def_out_diff','questionable_diff','wind_pass_diff','cold_pass_diff']
groups={'Efficiency + QB':feature_names[:11],'Injuries + coaching + rest':feature_names[:17],'Weather interactions':feature_names}
records=[];details={}
for g in all_sched:
 if g['season']<2023:continue
 live=pd.isna(g['home_score'])
 if live and str(g['espn']) not in [x['id'] for x in BASE['forecasts']]:continue
 f,detail=features(g,live);details[g['game_id']]=detail
 result=np.nan if live else int(g['home_score']>g['away_score']) if g['home_score']!=g['away_score'] else .5
 records.append({**g,**f,'target':result,'live':live})
frame=pd.DataFrame(records)
assert not frame.duplicated('game_id').any();assert not frame[feature_names].isna().any().any()
def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-35,35)))
def fit(train,names,alpha):
 x=train[names].to_numpy(float);y=train.target.to_numpy(float);mean=x.mean(axis=0);std=x.std(axis=0);std[std<1e-8]=1.;z=(x-mean)/std;z=np.column_stack([np.ones(len(z)),z]);beta=np.zeros(z.shape[1]);penalty=np.eye(len(beta))*alpha;penalty[0,0]=1e-6
 for iteration in range(50):
  p=sigmoid(z@beta);weights=np.maximum(p*(1-p),1e-6);gradient=z.T@(p-y)+penalty@beta;hessian=(z.T*weights)@z+penalty
  step=np.linalg.solve(hessian,gradient);beta-=step
  if np.max(np.abs(step))<1e-7:break
 return {'names':names,'mean':mean,'std':std,'beta':beta,'alpha':alpha,'iterations':iteration+1}
def predict(model,test):
 x=test[model['names']].to_numpy(float);return sigmoid(np.column_stack([np.ones(len(x)),(x-model['mean'])/model['std']])@model['beta'])
def scores(y,p):
 y=np.asarray(y);p=np.asarray(p);n=len(y);correct=int(((p>=.5)==y).sum());return {'games':n,'correct':correct,'accuracy':correct/n,'brier':float(np.mean((p-y)**2)),'logloss':float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))}
def rolling(year,names,alpha):
 parts=[]
 for week in sorted(frame.loc[frame.season.eq(year)&~frame.live,'week'].unique()):
  tr=frame[(frame.season.lt(year)|(frame.season.eq(year)&frame.week.lt(week)))&frame.target.isin([0,1])]
  te=frame[frame.season.eq(year)&frame.week.eq(week)&frame.target.isin([0,1])]
  m=fit(tr,names,alpha);tmp=te[['game_id','week','target']].copy();tmp['p']=predict(m,te);parts.append(tmp)
 return pd.concat(parts,ignore_index=True)
tuning=[]
for group,names in groups.items():
 for alpha in [3.,15.,60.]:
  val=rolling(2025,names,alpha);tuning.append({'model':group,'alpha':alpha,**scores(val.target,val.p)})
best_prior_model=min(tuning,key=lambda x:x['brier'])
# The expanded feature family follows the user's requested scope. Only its
# regularization is selected on 2025. The 2026 comparisons remain exploratory.
selected=min((x for x in tuning if x['model']=='Weather interactions'),key=lambda x:x['brier']);print('Expanded model, 2025 penalty selection',selected,flush=True)
evaluations=[];backtests={}
for group,names in groups.items():
 best=min((x for x in tuning if x['model']==group),key=lambda x:x['brier']);test=rolling(2026,names,best['alpha']);backtests[group]=test;evaluations.append({'model':group,'alpha':best['alpha'],**scores(test.target,test.p)})
chosen=selected['model'];test=backtests[chosen]
basep=[];basey=[];baseids=[]
for g in BASE['games']:
 if g['status']=='Final' and g['result']!=.5:basep.append(g['homeProb']);basey.append(g['result']);baseids.append(g['id'])
evaluations.append({'model':'Original Elo',**scores(basey,basep)})
train=frame[frame.target.isin([0,1])];model=fit(train,groups[chosen],selected['alpha']);upcoming=frame[frame.live].copy();upcoming['prob']=predict(model,upcoming)
forecast=[]
for r in upcoming.to_dict('records'):
 gid=r['game_id'];x=details[gid];p=r['prob'];g=next(g for g in BASE['forecasts'] if g['id']==str(r['espn']))
 standardized=(np.array([r[n] for n in model['names']])-model['mean'])/model['std'];contrib=standardized*model['beta'][1:]
 drivers=sorted([{'feature':n,'log_odds_home':v,'raw_value':r[n]} for n,v in zip(model['names'],contrib)],key=lambda x:abs(x['log_odds_home']),reverse=True)
 variants=[]
 for variant,kwargs in [('All questionable unavailable',{'allqout':True}),('Home backup QB',{'backup_side':'home'}),('Away backup QB',{'backup_side':'away'})]+([('Roof open',{'roof_open':True})] if r['home_team'] in RETRACT else []):
  vf,_=features(r,True,**kwargs);vp=float(predict(model,pd.DataFrame([vf]))[0]);variants.append({'scenario':variant,'home_probability':vp})
 forecast.append({'game_id':gid,'espn_id':str(r['espn']),'date':g['date'],'kickoff':g['time'],'away':r['away_team'],'home':r['home_team'],'pick':r['home_team'] if p>=.5 else r['away_team'],'home_probability':p,'pick_probability':max(p,1-p),
  'original_elo_home_probability':g['homeProb'],'original_elo_pick':g['pick'],'away_qb':x['away_qb'],'home_qb':x['home_qb'],'away_injury':x['away_injury'],'home_injury':x['home_injury'],
  'home_state':x['home_state'],'away_state':x['away_state'],'roof':x['roof'],'weather':weather_byid[str(r['espn'])],'features':{n:r[n] for n in feature_names},'drivers':drivers,'scenarios':variants})
team_metrics=[];qb_metrics=[]
for t in BASE['teams']:
 code=t['code'];state=team_state(code,2026,10);pid,qn=projected(code);q=qb_state(pid,2026,10);q['name']=qn
 team_metrics.append({'team':code,'name':t['name'],**state,**injuries_for(code,2026,10,True),'projected_qb':qn})
 qb_metrics.append({'team':code,**q})
for i in CTX['injuries']:
 pid=espnmap.get(str(i['espn_id'])) or namemap.get(namekey(i['player']));off,deff=snapweight(i['team'],pid,2026,10);i['prior_off_snap_share']=off;i['prior_def_snap_share']=deff;i['gsis_id']=pid
backtest_rows=test.merge(frame[['game_id','espn','away_team','home_team']],on='game_id').to_dict('records')
weekly=[]
for week,v in test.groupby('week'):weekly.append({'week':int(week),**scores(v.target,v.p)})
calibration=[]
for low,high in [(0,.4),(.4,.5),(.5,.6),(.6,.7),(.7,1.0001)]:
 v=test[test.p.ge(low)&test.p.lt(high)]
 if len(v):calibration.append({'bin':f'{low:.0%}–{min(high,1):.0%}','games':len(v),'mean_home_probability':v.p.mean(),'home_win_rate':v.target.mean()})
unknown_qbs=[q for q in qb_metrics if q['dropbacks']<30]
output={'version':'2.0','as_of':'2026-11-10','selected':selected,'best_prior_feature_family':best_prior_model,'selection_policy':'Expanded feature family follows requested scope. Penalty selected on 2025 Brier score. 2026 comparisons are exploratory retrospective checks.','evaluations':evaluations,'tuning_2025':tuning,'forecast':forecast,'team_metrics':team_metrics,'qb_metrics':qb_metrics,
 'staff':CTX['staff'],'injuries':CTX['injuries'],'weekly':weekly,'calibration':calibration,'backtest':backtest_rows,
 'model':{k:native(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in model.items()},
 'quality':{'source_counts':source_counts,'2026_games_reconciled':136,'2026_decisive_evaluated':135,'training_games':len(train),'unique_player_map_rate':float(snaps.pid.notna().mean()),'future_forecasts':len(forecast),'ambiguous_injury_rows_excluded':ambiguous_injury_rows,'injury_report_latest_week':int(injury[injury.season.eq(2026)].week.max()),'low_sample_qbs':[{'team':q['team'],'name':q['name'],'dropbacks':q['dropbacks']} for q in unknown_qbs]},
 'limitations':['Current projected starters are from ESPN depth charts and current injury statuses. Recheck the final inactive list.',
 'Historical evaluation assumes the recorded starting QB was known before kickoff. No statistics from that game enter its features.',
 'Historical injury inputs are final weekly reports without issuance timestamps. Current inputs are Tuesday ESPN statuses, not final Week 10 game designations.',
 'Recent snap shares proxy player importance. Low or absent recent participation can understate the loss of a player. IR status coverage differs between sources.',
 'Weather interactions use historical observed game weather. Those results do not validate the accuracy of pregame weather forecasts.',
 'Forecasts use city-level Open-Meteo conditions nearest kickoff. Retractable roofs are assumed closed and have an open-roof scenario.',
 'HC changes enter as a feature. OC/DC names and scheme statistics are tracked as context, without invented coordinator rankings or causal coaching grades.',
 'The expanded feature family follows the requested scope. 2025 selects its penalty. 2026 is an exploratory rolling retrospective comparison, not a prospectively locked trial. The simpler feature family performed slightly better in 2025.',
 'EPA and CPOE are derived nflfastR model outputs. Public revised data may differ from what was available at the original prediction time.',
 'Scenario probabilities are sensitivity checks, not confidence intervals. Rookie/low-sample QBs require particular caution.',
 'Ties are excluded from binary training and evaluation. Forecast probabilities are conditional on a decisive result.'],
 'sources':[{'name':'nflverse play-by-play 2022–2026','url':'https://github.com/nflverse/nflverse-data/releases/tag/pbp'},{'name':'nflverse schedules','url':'https://github.com/nflverse/nfldata/blob/master/data/games.csv'},{'name':'nflverse injury reports','url':'https://github.com/nflverse/nflverse-data/releases/tag/injuries'},{'name':'nflverse snap counts','url':'https://github.com/nflverse/nflverse-data/releases/tag/snap_counts'},{'name':'ESPN live depth charts / injuries','url':'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/33/depthcharts'},{'name':'Open-Meteo hourly forecasts','url':'https://open-meteo.com/en/docs'}]}
(ROOT/'model.json').write_text(json.dumps(native(output),indent=2,allow_nan=False))
frame.to_csv(ROOT/'pregame_features.csv',index=False)
print(json.dumps(native({'selected':selected,'evaluations':evaluations,'forecast':[{'game':x['away']+' @ '+x['home'],'pick':x['pick'],'p':x['pick_probability'],'qb':x['away_qb']['name']+' / '+x['home_qb']['name']} for x in forecast],'quality':output['quality']}),indent=2))
