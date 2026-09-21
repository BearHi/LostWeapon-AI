import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_075322'/'refined';OUT.mkdir(exist_ok=True)
windows=[('jump',1.3,1.5),('ground',27.08,27.26),('back1',38.7,38.9),('back2',41.9,42.15),('backhold',51.68,51.9),('front',62.45,62.7),('fronthold',84.35,84.6),('chute',104.12,104.35),('combo',130.33,130.6)]
cap=cv2.VideoCapture(r'C:\Users\microsoft\Videos\2026-09-06 07-53-22.mp4')
for label,start,end in windows:
    first,last=round(start*60),round(end*60);cap.set(cv2.CAP_PROP_POS_FRAMES,first)
    sheet=Image.new('RGB',(330*4,155*((last-first+4)//4)),(25,25,25));d=ImageDraw.Draw(sheet)
    for j,frame in enumerate(range(first,last+1)):
        ok,im=cap.read()
        if not ok:break
        crop=Image.fromarray(cv2.cvtColor(im[650:1030,540:870],cv2.COLOR_BGR2RGB));crop.save(OUT/f'f{frame:06d}.png')
        x=j%4*330;y=j//4*155;sheet.paste(crop.crop((0,155,330,280)),(x,y+30));d.text((x+4,y+5),f'{label} {frame/60:.4f}s f{frame}',fill='white')
    sheet.save(OUT/f'{label}.jpg',quality=97)
    print(label,flush=True)
cap.release()
