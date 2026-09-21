import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2,numpy as np
from PIL import Image,ImageDraw
OUT=Path(__file__).parent/'motion_075322'
KEYS={'left':(918,1494,938,1510),'right':(1030,1494,1050,1510),
      'up':(975,1440,990,1455),'down':(975,1494,990,1510),'c':(473,1438,488,1453)}
def extract(video):
    cap=cv2.VideoCapture(video);fps=cap.get(cv2.CAP_PROP_FPS);rows=[];out=OUT/'crops';out.mkdir(exist_ok=True,parents=True)
    i=0
    while True:
        ok,im=cap.read()
        if not ok:break
        keys={}
        for k,(x1,y1,x2,y2) in KEYS.items():
            px=im[y1:y2,x1:x2].astype(float);b,g,r=cv2.mean(px)[:3];keys[k]=bool(g>r*1.3 and g>80)
        # Preserve every source frame's keyboard state.
        rows.append({'frame':i,'time_s':round(i/fps,6),**keys})
        if i%3==0:
            crop=im[650:1030,620:850]
            Image.fromarray(cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)).save(out/f'f{i:06d}.png')
        i+=1
    (OUT/'keys.json').write_text(json.dumps(rows),encoding='utf-8');print('frames',i,flush=True)
    cap.release()
if __name__=='__main__':extract(sys.argv[1])
