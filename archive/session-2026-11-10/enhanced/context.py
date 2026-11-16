from pathlib import Path
from html.parser import HTMLParser
from urllib.request import urlopen,Request
from urllib.parse import urlencode
import json,re,datetime,html
ROOT=Path(__file__).resolve().parent
BASE=json.loads((ROOT.parent/'analysis.json').read_text())
class Text(HTMLParser):
 def __init__(self):super().__init__();self.tokens=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ['script','style']:self.skip+=1
 def handle_endtag(self,tag):
  if tag in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip and data.strip():self.tokens.append(' '.join(data.split()))
def readjson(name):return json.loads((ROOT/'raw'/name).read_text())
def fetch(name,url):
 path=ROOT/'raw'/name
 if not path.exists():
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=40) as response:path.write_bytes(response.read())
 return json.loads(path.read_text())
staff=[];depth=[];injuries=[];weather=[]
manifest=readjson('../collection.json') if False else json.loads((ROOT/'collection.json').read_text())
for team in BASE['teams']:
 code=team['code'];raw=(ROOT/'raw'/f'staff_{code}.html').read_text();p=Text();p.feed(raw);tokens=p.tokens
 row={'team':code,'head_coach':None,'offensive_coordinator':None,'defensive_coordinator':None,'source':next((x['url'] for x in manifest if x['file']==f'staff_{code}.html'),'')}
 if code=='CHI':row['source']='https://www.chicagobears.com/team/coaches/'
 for key,role in [('head_coach','Head Coach'),('offensive_coordinator','Offensive Coordinator'),('defensive_coordinator','Defensive Coordinator')]:
  for i,x in enumerate(tokens):
   if x==role or x.startswith(role+'/') or x.startswith(role+' /'):
    nxt=tokens[i+1] if i+1<len(tokens) else ''
    if 2<=len(nxt.split())<=4 and len(nxt)<50 and nxt!=role and not nxt.startswith('Experience'):
     row[key]=nxt;break
 for match in re.finditer(r'<h3[^>]*class="[^"]*d3-o-media-object__title[^"]*"[^>]*>([^<]{1,60})</h3>\s*<h[45][^>]*>([^<]{1,100})</h[45]>',raw,re.S):
  name=html.unescape(re.sub('<[^>]+>','',match.group(1))).strip();role=html.unescape(re.sub('<[^>]+>','',match.group(2))).strip()
  if role=='Head Coach':row['head_coach']=name
  if 'Offensive Coordinator' in role and not role.startswith('Assistant Offensive Coordinator'):row['offensive_coordinator']=name
  if 'Defensive Coordinator' in role and not role.startswith('Assistant Defensive Coordinator'):row['defensive_coordinator']=name
 if code=='CAR':
  row['defensive_coordinator']='Todd Wash (interim)';row['coordinator_update_source']='https://amp.nfl.com/news/panthers-fire-defensive-coordinator-ejiro-evero';row['change_note']='Interim DC appointed October 30, 2026. Recent defensive averages span both coordinators.'
 if code=='WSH':
  row['offensive_coordinator']='David Blough';row['coordinator_update_source']='https://www.commanders.com/news/commanders-name-david-blough-offensive-coordinator'
 if code=='TB':row['defensive_coordinator']='No separate DC listed'
 for k in ['head_coach','offensive_coordinator','defensive_coordinator']:
  if row[k]:row[k]=row[k].replace('\ufffd',"'")
 staff.append(row)
 d=readjson(f'depth_{code}.json')
 for group in d.get('depthchart',[]):
  for pos,entry in group.get('positions',{}).items():
   for rank,a in enumerate(entry.get('athletes',[])):
    depth.append({'team':code,'position':pos.upper(),'rank':rank+1,'name':a['displayName'],'espn_id':a['id'],'injuries':a.get('injuries',[])})
for g in BASE['forecasts']:
 s=readjson(f'summary_{g["id"]}.json')
 for item in s.get('injuries',[]):
  for i in item.get('injuries',[]):
   if i.get('date','')>'2026-11-11T05:00Z':continue
   a=i.get('athlete',{});injuries.append({'game_id':g['id'],'team':item['team']['abbreviation'],'player':a.get('displayName'),
    'position':a.get('position',{}).get('abbreviation'),'status':i.get('status'),'updated':i.get('date'),'injury':i.get('details',{}).get('type'),
    'espn_id':a.get('id'),'source':f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={g["id"]}'})
 address=s.get('gameInfo',{}).get('venue',{}).get('address',{});city=address.get('city');country=address.get('country','USA');geo_url='https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':city,'count':20,'language':'en','format':'json','countryCode':'DE' if country=='Germany' else 'US'})
 try:
  geo=fetch(f'geo_{g["home"]}.json',geo_url);locations=geo.get('results',[])
  preferred=[x for x in locations if x.get('country_code')==('DE' if country=='Germany' else 'US')]
  if not preferred:raise ValueError('City coordinates unavailable')
  loc=preferred[0];lat,lon=loc['latitude'],loc['longitude']
  params={'latitude':lat,'longitude':lon,'hourly':'temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,precipitation','temperature_unit':'fahrenheit','wind_speed_unit':'mph','precipitation_unit':'inch','timezone':'UTC','start_date':'2026-11-15','end_date':'2026-11-17'}
  url='https://api.open-meteo.com/v1/forecast?'+urlencode(params);forecast=fetch(f'weather_{g["id"]}.json',url);hourly=forecast['hourly']
  times=[datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc) for t in hourly['time']];kickoff=datetime.datetime.fromisoformat(g['kickoff'].replace('Z','+00:00'));idx=min(range(len(times)),key=lambda i:abs((times[i]-kickoff).total_seconds()))
  weather.append({'game_id':g['id'],'city':city,'latitude':lat,'longitude':lon,'valid_utc':hourly['time'][idx],
    'temperature_f':hourly['temperature_2m'][idx],'wind_mph':hourly['wind_speed_10m'][idx],'gust_mph':hourly['wind_gusts_10m'][idx],
    'precip_probability':hourly['precipitation_probability'][idx]/100,'precip_in':hourly['precipitation'][idx],'source':url,'coordinate_source':geo_url,'scope':'City-level hourly forecast, nearest kickoff hour'})
 except Exception as error:weather.append({'game_id':g['id'],'city':city,'error':str(error),'source':geo_url})
slate_teams={g[side] for g in BASE['forecasts'] for side in ['home','away']}
combined={(i['team'],str(i['espn_id'])):i for i in injuries}
for r in depth:
 if r['team'] not in slate_teams:continue
 pos=r['position'];pos='WR' if pos.startswith('WR') else 'TE' if pos in ['LTE','RTE','TE'] else 'OL' if pos in ['LT','LG','C','RG','RT','T','G','OL'] else 'RB' if pos in ['RB','HB'] else pos
 game=next(g for g in BASE['forecasts'] if r['team'] in [g['away'],g['home']])
 for injury in r['injuries']:
  if injury.get('date','')>'2026-11-11T05:00Z':continue
  key=(r['team'],str(r['espn_id']))
  if key in combined and combined[key].get('updated','')>=injury.get('date',''):continue
  combined[key]={'game_id':game['id'],'team':r['team'],'player':r['name'],'position':pos,'status':injury.get('status'),'updated':injury.get('date'),
   'injury':injury.get('details',{}).get('type'),'espn_id':r['espn_id'],'source':next((x['url']for x in manifest if x['file']==f'depth_{r["team"]}.json'),'')}
injuries=list(combined.values())
result={'staff':staff,'depth':depth,'injuries':injuries,'weather':weather,'as_of':'2026-11-10','retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(ROOT/'context.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'staff_missing':[r for r in staff if any(not r[k] for k in ['head_coach','offensive_coordinator','defensive_coordinator'])],
 'injuries':len(injuries),'weather_available':sum('temperature_f' in w for w in weather)},indent=2))
