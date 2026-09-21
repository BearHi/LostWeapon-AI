"""Extract keys and coordinate text crops from 18:06 source; never use bottom HUD.

Coordinates are OCR candidates until visually checked against saved source crops.
"""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2
import numpy as np
from PIL import Image,ImageDraw
from rapidocr_onnxruntime import RapidOCR

OUT=Path(__file__).parent/'motion_180606'
VIDEO=r'C:\Users\microsoft\Videos\2026-09-06 18-06-06.mp4'
KEYS={'left':(918,1494,938,1510),'right':(1030,1494,1050,1510),
      'up':(975,1440,990,1455),'down':(975,1494,990,1510),'c':(473,1438,488,1453)}


def main():
    cap=cv2.VideoCapture(VIDEO)
    fps=cap.get(cv2.CAP_PROP_FPS)
    rows=[]; keys=[]; text_images=[]; indexes=[]
    cropdir=OUT/'coordinate_crops'; cropdir.mkdir(parents=True,exist_ok=True)
    i=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        pressed={}
        for k,(x1,y1,x2,y2) in KEYS.items():
            b,g,r=cv2.mean(frame[y1:y2,x1:x2])[:3]
            pressed[k]=bool(g>r*1.3 and g>80)
        keys.append({'frame':i,'time_s':round(i/fps,4),**pressed})
        if i%6==0:
            # Yellow character-adjacent numbers, within the game image only.
            roi=frame[450:1170,70:1275]
            b,g,r=[roi[:,:,j].astype(float) for j in range(3)]
            mask=((r>145)&(g>155)&(g>r*.94)&(b<155)&(g>b*1.6)).astype('uint8')*255
            grouped=cv2.dilate(mask,np.ones((3,13),np.uint8))
            contours,_=cv2.findContours(grouped,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            boxes=[]
            for c in contours:
                x,y,w,h=cv2.boundingRect(c)
                if 58<=w<=200 and 10<=h<=29:
                    boxes.append((max(0,x-3),max(0,y-3),min(roi.shape[1],x+w+3),min(roi.shape[0],y+h+3)))
            boxes.sort(key=lambda z:(z[1],z[0]))
            row={'frame':i,'time_s':round(i/fps,4),'lines':[]}
            rows.append(row)
            # Small source crops retain the coordinate colors and nearby scene.
            for j,(x1,y1,x2,y2) in enumerate(boxes):
                sub=roi[y1:y2,x1:x2]
                text_images.append(sub); indexes.append((len(rows)-1,len(row['lines'])))
                row['lines'].append({'screen_box':[x1+70,y1+450,x2+70,y2+450]})
                Image.fromarray(cv2.cvtColor(sub,cv2.COLOR_BGR2RGB)).save(cropdir/f'f{i:06d}_{j}.png')
        i+=1
    cap.release()
    (OUT/'keys.json').write_text(json.dumps(keys),encoding='utf-8')
    events=[]
    for key in KEYS:
        start=None
        for row in keys+[{'frame':len(keys),key:False}]:
            if row[key] and start is None:start=row['frame']
            if not row[key] and start is not None:
                events.append({'key':key,'start_frame':start,'end_frame':row['frame']-1,
                               'start_s':round(start/fps,4),'end_s':round(row['frame']/fps,4)})
                start=None
    (OUT/'key_events.json').write_text(json.dumps(sorted(events,key=lambda e:e['start_frame']),indent=2),encoding='utf-8')
    print(f'decoded {i} frames; OCR {len(text_images)} lines',flush=True)
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    for start in range(0,len(text_images),48):
        result,_=engine.text_rec(text_images[start:start+48])
        for rec,(ri,li) in zip(result,indexes[start:start+48]):
            raw,conf=rec
            rows[ri]['lines'][li].update(raw=raw,confidence=float(conf))
        if start%240==0:print('OCR',start,'/',len(text_images),flush=True)
    (OUT/'coordinate_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('done',flush=True)


if __name__=='__main__':main()
