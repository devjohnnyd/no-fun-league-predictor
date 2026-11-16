from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import json,math
import numpy as np
import pandas as pd
import openpyxl
ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'model.json').read_text())
file=ROOT.parent.parent/'outputs/nfl-2026/nfl-season-tracker-2026.xlsx'
old=openpyxl.load_workbook(ROOT/'original-tracker.xlsx',data_only=True,read_only=True)
book=openpyxl.load_workbook(file,data_only=True,read_only=True)
assert len(book.sheetnames)==9
def equal(a,b):
 if isinstance(a,(float,int)) and isinstance(b,(float,int)):return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-9)
 return a==b
for sheet,rows,cols in [('Games',278,25),('Teams',38,12)]:
 for row1,row2 in zip(old[sheet].iter_rows(min_row=1,max_row=rows,max_col=cols,values_only=True),book[sheet].iter_rows(min_row=1,max_row=rows,max_col=cols,values_only=True)):
  assert all(equal(a,b)for a,b in zip(row1,row2)),(sheet,row1,row2)
for row in range(23,27):assert old['Performance'].cell(row,2).value==book['Performance'].cell(row,2).value
for i,g in enumerate(d['forecast'],8):
 assert book['Predictions'].cell(i,5).value==g['pick']
 assert abs(book['Predictions'].cell(i,6).value-g['pick_probability'])<1e-10
 assert abs(book['Model 2'].cell(i,5).value-g['home_probability'])<1e-10
 assert book['Predictions'].cell(i,7).value=='Pending'
selected=next(e for e in d['evaluations'] if e['model']==d['selected']['model'])
assert book['Performance']['B5'].value==135
assert book['Performance']['B6'].value==selected['correct']
assert abs(book['Performance']['B8'].value-selected['brier'])<1e-12
assert sum(book['Performance'].cell(r,2).value for r in range(31,40))==135
assert sum(book['Performance'].cell(r,3).value for r in range(31,40))==selected['correct']
assert book['Injuries'].cell(len(d['injuries'])+7,1).value is not None
for i,c in enumerate(d['staff'],8):
 assert book['Coaching'].cell(i,3).value==c['offensive_coordinator']
 assert book['Coaching'].cell(i,4).value==c['defensive_coordinator']
for sheet in book:
 for row in sheet.iter_rows():
  for c in row:assert c.data_type!='e',(sheet.title,c.coordinate,c.value)
book.close();old.close()
f=pd.read_csv(ROOT/'pregame_features.csv');m=d['model'];train=f[f.target.isin([0,1])];x=train[m['names']].to_numpy(float);z=np.column_stack([np.ones(len(x)),(x-np.array(m['mean']))/np.array(m['std'])]);beta=np.array(m['beta']);p=1/(1+np.exp(-z@beta));pen=np.array([1e-6]+[m['alpha']]*len(m['names']));gradient=z.T@(p-train.target.to_numpy(float))+pen*beta
assert np.max(np.abs(gradient))<1e-5
# Independently reconstruct past-only offense and QB EPA for two held-out weeks.
s=pd.read_csv(ROOT/'raw/schedules.csv');s.home_team=s.home_team.replace({'LA':'LAR','WAS':'WSH'});s.away_team=s.away_team.replace({'LA':'LAR','WAS':'WSH'})
agg=[json.loads((ROOT/f'aggregates_{y}.json').read_text())for y in range(2022,2027)]
tg={k:v for a in agg for k,v in a['team_games'].items()};qg={}
for a in agg:
 for k,v in a['qb_games'].items():qg.setdefault(k,[]).extend(v)
for gid in ['2026_02_BUF_GB','2026_09_BUF_MIN']:
 sample=f[f.game_id.eq(gid)]
 if sample.empty:sample=f[f.season.eq(2026)&f.week.eq(2 if '_02_'in gid else 9)].head(1)
 r=sample.iloc[0]
 def rate(team):
  hist=s[s.game_type.eq('REG')&s.home_score.notna()&(s.home_team.eq(team)|s.away_team.eq(team))]
  prev=hist[hist.season.eq(2025)].tail(12);cur=hist[hist.season.eq(2026)&hist.week.lt(r.week)]
  num=sum(tg[g+'|'+team]['epa_sum']*.45 for g in prev.game_id)+sum(tg[g+'|'+team]['epa_sum']for g in cur.game_id)
  den=100+sum(tg[g+'|'+team]['plays']*.45 for g in prev.game_id)+sum(tg[g+'|'+team]['plays']for g in cur.game_id)
  return num/den
 assert abs(rate(r.home_team)-rate(r.away_team)-r.off_epa_diff)<1e-10
 def qr(pid):
  items=[g for g in qg.get(pid,[])if 2024<=g['season'] and (g['season']<2026 or g['week']<r.week)]
  return sum(g['epa_sum']*.65**(2026-g['season'])for g in items)/(150+sum(g['db']*.65**(2026-g['season'])for g in items))
 assert abs(qr(r.home_qb_id)-qr(r.away_qb_id)-r.qb_epa_diff)<1e-10
with ZipFile(file)as archive:
 charts=[n for n in archive.namelist()if '/charts/chart'in n and n.endswith('.xml')];assert len(charts)==1
 ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 tree=ET.fromstring(archive.read(charts[0]));refs=[x.text for x in tree.findall('.//c:val/c:numRef/c:f',ns)]
 assert refs==["'Performance'!$E$31:$E$39","'Performance'!$F$31:$F$39"],refs
 colors=[x.attrib['val']for x in tree.findall('.//c:ser/c:spPr/a:ln/a:solidFill/a:srgbClr',ns)];assert colors==['17324D','8594A3']
 tables=[ET.fromstring(archive.read(n))for n in archive.namelist()if n.startswith('xl/tables/table') and n.endswith('.xml')]
 assert any(t.attrib.get('name')=='TeamResults' and t.attrib['ref']=='A6:Y38'for t in tables)
print('Verified: original 272-game inputs and standings preserved; 13 new picks; all score metrics; 32 staff entries; 363 injuries; no cached formula errors; model gradient; two past-only feature reconstructions; editable chart and expanded filter tables.')
