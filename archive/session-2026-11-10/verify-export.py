import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl

root=Path(__file__).resolve().parent.parent
data=json.loads((root/'work/analysis.json').read_text())
path=root/'outputs/nfl-2026/nfl-season-tracker-2026.xlsx'
book=openpyxl.load_workbook(path,data_only=True,read_only=True)
assert book.sheetnames==['Predictions','Teams','Games','Performance']
assert book['Performance']['B5'].value==136
assert book['Performance']['B6'].value==135
assert book['Performance']['B7'].value==73
assert abs(book['Performance']['B9'].value-data['metrics']['brier'])<1e-12
assert sum(book['Performance'].cell(r,2).value for r in range(31,40))==128
for i,t in enumerate(data['teams'],7):
    vals=[book['Teams'].cell(i,c).value for c in range(1,13)]
    assert vals[0]==t['code']
    assert vals[2:8]==[t['played'],t['wins'],t['losses'],t['ties'],t['pointsFor'],t['pointsAgainst']]
    assert abs(vals[11]-t['elo'])<1e-8
for i,p in enumerate(data['forecasts'],8):
    assert book['Predictions'].cell(i,5).value==p['pick']
    assert abs(book['Predictions'].cell(i,6).value-p['pickProbability'])<1e-12
    assert book['Predictions'].cell(i,7).value=='Pending'
book.close()
ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with ZipFile(path) as archive:
    charts=[n for n in archive.namelist() if '/charts/chart' in n and n.endswith('.xml')]
    assert len(charts)==1
    tree=ET.fromstring(archive.read(charts[0]))
    colors=[e.attrib['val'] for e in tree.findall('.//c:ser/c:spPr/a:ln/a:solidFill/a:srgbClr',ns)]
    assert colors==['17324D','8594A3'],colors
    gamexml=ET.fromstring(archive.read('xl/worksheets/sheet3.xml'))
    date=gamexml.find('.//s:c[@r="C7"]',ns)
    assert date.attrib.get('t','n')=='n'
    assert float(date.find('s:v',ns).text)>40000
chart=(root/'work/nfl-week-10-picks.html').read_text()
payload=chart.split('data-viz-chart>')[1].split('</script>')[0]
rows=json.loads(payload)['rows']
assert len(rows)==13
for row,p in zip(rows,data['forecasts']):assert row[1]==p['pickProbability']
print('Export verified: all 32 team records, 13 forecasts, 128-game weekly comparison, numeric dates, chart bindings and series colors.')
