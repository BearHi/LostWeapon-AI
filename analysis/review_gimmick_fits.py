import json
from pathlib import Path
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_180606'/'refined'
rows=json.loads((OUT/'coordinates.json').read_text(encoding='utf-8'))
for name in ['M1','M2','M3','M4','I1','I2','I3','I4']:
    samples=[r for r in rows if r['trial']==name]
    im=Image.new('RGB',(220*5,175*((len(samples)+4)//5)),(25,25,25));d=ImageDraw.Draw(im)
    for i,r in enumerate(samples):
        x,y=i%5*220,i//5*175
        raw=next(l['raw'] for l in r['lines'] if l['axis']=='y')
        d.text((x+4,y+3),f"{r['frame']/60:.3f}s f{r['frame']} OCR:{raw}",fill='white')
        im.paste(Image.open(OUT/f"f{r['frame']:06d}.png"),(x+4,y+26))
    im.save(OUT/f'audit_{name}.jpg',quality=96)
