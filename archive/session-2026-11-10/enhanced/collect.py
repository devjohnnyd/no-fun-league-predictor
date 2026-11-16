from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import urlopen,Request
import json,time
ROOT=Path(__file__).resolve().parent
base=json.loads((ROOT.parent/'analysis.json').read_text())
domains={'ARI':'azcardinals.com','ATL':'atlantafalcons.com','BAL':'baltimoreravens.com','BUF':'buffalobills.com','CAR':'panthers.com','CHI':'chicagobears.com','CIN':'bengals.com','CLE':'clevelandbrowns.com','DAL':'dallascowboys.com','DEN':'denverbroncos.com','DET':'detroitlions.com','GB':'packers.com','HOU':'houstontexans.com','IND':'colts.com','JAX':'jaguars.com','KC':'chiefs.com','LAC':'chargers.com','LAR':'therams.com','LV':'raiders.com','MIA':'miamidolphins.com','MIN':'vikings.com','NE':'patriots.com','NO':'neworleanssaints.com','NYG':'giants.com','NYJ':'newyorkjets.com','PHI':'philadelphiaeagles.com','PIT':'steelers.com','SEA':'seahawks.com','SF':'49ers.com','TB':'buccaneers.com','TEN':'tennesseetitans.com','WSH':'commanders.com'}
jobs=[]
for t in base['teams']:
 code=t['code'];g=next(g for g in base['games'] if code in (g['away'],g['home']));tid=g['homeId'] if code==g['home'] else g['awayId']
 jobs += [(f'depth_{code}.json',f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/depthcharts'),(f'staff_{code}.html',f'https://www.{domains[code]}/team/coaches-roster/')]
for g in base['forecasts']:jobs.append((f'summary_{g["id"]}.json',f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={g["id"]}'))
jobs.append(('coaches-guide.pdf','https://g.espncdn.com/s/ffldraftkit/26/NFLDK2026_CS_ClayProjections2026.pdf'))
def get(job):
 name,url=job;path=ROOT/'raw'/name
 try:
  if not path.exists():
   req=Request(url,headers={'User-Agent':'Mozilla/5.0 NFL statistical research'})
   with urlopen(req,timeout=40) as response:content=response.read()
   path.write_bytes(content)
  return {'file':name,'url':url,'bytes':path.stat().st_size,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'ok'}
 except Exception as error:return {'file':name,'url':url,'status':'error','error':str(error)}
with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(get,jobs))
(ROOT/'collection.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'files':len(results),'success':sum(x['status']=='ok' for x in results),'errors':[x for x in results if x['status']!='ok']},indent=2))
