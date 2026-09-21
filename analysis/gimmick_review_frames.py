"""Source screenshots at the sampled launch/apex intervals; preserve raw text."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_180606'
cap=cv2.VideoCapture(r'C:\Users\microsoft\Videos\2026-09-06 18-06-06.mp4')
keys=json.loads((OUT/'keys.json').read_text())
groups={'launch_first':[1914,1915,1918,1920],
        'peak_first':[1977,1980,1983,1986],
        'launch_second':[2460,2462,2464,2466],
        'peak_second':[2502,2508,2514,2532],
        'late':[2870,2872,2904,2910]}
for label,frames in groups.items():
    sheet=Image.new('RGB',(1210,400*len(frames)),(25,25,25));d=ImageDraw.Draw(sheet)
    for n,f in enumerate(frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES,f);ok,bgr=cap.read()
        if not ok:continue
        im=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        im.save(OUT/f'review_f{f:06d}.jpg',quality=96)
        crop=im.crop((70,790,1280,1160))
        sheet.paste(crop,(0,n*400+30))
        pressed=','.join(k for k in ['up','down','left','right','c'] if keys[f][k])
        d.text((5,n*400+5),f'{f/60:.4f}s frame {f} keys:{pressed}',fill='white')
    sheet.save(OUT/f'review_{label}.jpg',quality=96)
cap.release()
