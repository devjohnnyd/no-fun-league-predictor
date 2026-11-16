from pathlib import Path
import json,re
root=Path(__file__).resolve().parent
model=json.loads((root/'model.json').read_text())
file=root.parent/'nfl-week-10-picks.html'
text=file.read_text()
m=re.search(r'(<script type="application/json" data-viz-chart>)(.*?)(</script>)',text,re.S)
config=json.loads(m.group(2))
names={'NE':'Patriots','DET':'Lions','BUF':'Bills','NYJ':'Jets','CAR':'Panthers','NO':'Saints','HOU':'Texans','CLE':'Browns','JAX':'Jaguars','TEN':'Titans','KC':'Chiefs','ATL':'Falcons','MIA':'Dolphins','IND':'Colts','MIN':'Vikings','GB':'Packers','LAR':'Rams','ARI':'Cardinals','SEA':'Seahawks','LV':'Raiders','SF':'49ers','DAL':'Cowboys','PIT':'Steelers','CIN':'Bengals','LAC':'Chargers','BAL':'Ravens'}
config['title']='Week 10 updated model picks'
config['description']='November 15–16, 2026. Model 2 includes projected QBs, snap-weighted injuries, team efficiency, rest, HC changes and wind/temperature interactions. Tuesday statuses and roof assumptions remain provisional. Ties are not modeled.'
config['rows']=[[('Monday ' if g['date']=='2026-11-16' else 'Sunday night ' if g['away']=='PIT' else '')+names[g['away']]+' at '+names[g['home']]+': '+names[g['pick']],g['pick_probability']] for g in model['forecast']]
text=text[:m.start(2)]+'\n'+json.dumps(config,indent=2)+'\n'+text[m.end(2):]
file.write_text(text)
assert len(config['rows'])==13
assert all(row[1]==g['pick_probability'] for row,g in zip(config['rows'],model['forecast']))
print('Updated 13 inline forecasts to Model 2.')
