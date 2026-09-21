"""Show unmodified character-side text crops for visual review."""
from pathlib import Path
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_180606'
for name,start,end in [('ice_first',31.5,34.2),('ice_second',40.6,43.3),('late_jump',47.6,49.6),('magnet_first',1.5,3.8)]:
    frames=list(range(round(start*60),round(end*60)+1,6))
    sheet=Image.new('RGB',(280*5,170*((len(frames)+4)//5)),(25,25,25))
    d=ImageDraw.Draw(sheet)
    for i,f in enumerate(frames):
        xx,yy=i%5*280,i//5*170
        d.text((xx+4,yy+4),f'{f/60:.2f}s / frame {f}',fill='white')
        for j,p in enumerate(sorted((OUT/'coordinate_crops').glob(f'f{f:06d}_*.png'))[:4]):
            im=Image.open(p)
            sheet.paste(im,(xx+4,yy+23+j*35))
    sheet.save(OUT/f'evidence_{name}.png')
