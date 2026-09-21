import json
from pathlib import Path
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_075322'
events=[('jump',.867,2.0),('jumpmove',9.167,10.35),('groundroll',26.583,28.2),
('backrelease',38.067,39.95),('backhold',50.967,52.95),('frontrelease',61.9,63.9),
('fronthold',83.833,85.1),('parachute',103.683,105.8),('combo',129.583,132.2)]
keys=json.loads((OUT/'keys.json').read_text(encoding='utf-8'))
for label,start,end in events:
    frames=list(range(round(start*60/3)*3,round(end*60),6))
    sheet=Image.new('RGB',(230*5,180*((len(frames)+4)//5)),(25,25,25));d=ImageDraw.Draw(sheet)
    for j,f in enumerate(frames):
        path=OUT/'crops'/f'f{f:06d}.png'
        if not path.exists():continue
        im=Image.open(path).crop((0,130,230,280));x=j%5*230;y=j//5*180
        sheet.paste(im,(x,y+30));pressed=','.join(k for k in ['up','down','left','right','c'] if keys[f][k])
        d.text((x+3,y+3),f'{f/60:.3f}s f{f} {pressed}',fill='white')
    sheet.save(OUT/f'event_{label}.jpg',quality=95)
