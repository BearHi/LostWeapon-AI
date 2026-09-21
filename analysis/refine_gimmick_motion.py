"""Track the blue-hatted player's health bar; recover complete coordinate lines.

All quantities remain video-derived candidates; fits never cross a roll input.
"""
import sys,json,re,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2
import numpy as np
from PIL import Image,ImageDraw
from rapidocr_onnxruntime import RapidOCR

ROOT=Path(__file__).parent/'motion_180606'
OUT=ROOT/'refined';OUT.mkdir(exist_ok=True)
VIDEO=r'C:\Users\microsoft\Videos\2026-09-06 18-06-06.mp4'
WINDOWS=[('M1',96,210,140),('M2',444,570,485),('M3',807,942,860),
         ('M4',1125,1239,1172),('I1',1908,2040,1958),('I2',2457,2580,2521),
         ('I3',2865,3006,2929),('I4',3045,3186,3093)]


def anchor(frame):
    roi=frame[400:1175,70:1278]
    b,g,r=cv2.split(roi)
    mask=((b>155)&(g>160)&(r<115)).astype('uint8')*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        if not (60<=w<=130 and 5<=h<=18):continue
        patch=roi[max(0,y-230):max(1,y-25),max(0,x-90):min(roi.shape[1],x+180)]
        bb,gg,rr=cv2.split(patch)
        score=int(((bb.astype(float)>rr*1.07)&(bb>130)&(gg>100)).sum())
        candidates.append((score,x+70,y+400,w,h))
    return max(candidates) if candidates else None


def read_extract(preview_only=False, edges=False):
    cv2.setNumThreads(1)
    cap=cv2.VideoCapture(VIDEO)
    samples=[];texts=[]
    if preview_only:
        frames=(1916,1917,1918,2464,2465,2872,2873,2874,3051,3052) if edges else (102,450,813,1129,1915,1980,2464,2508,2872,2952)
        windows=[('check',f,f,0) for f in frames]
    else:windows=WINDOWS
    for name,start,end,roll in windows:
        cap.set(cv2.CAP_PROP_POS_FRAMES,start)
        for f in range(start,end+1):
            ok,frame=cap.read()
            if not ok:break
            if not preview_only and (f-start)%3:continue
            found=anchor(frame)
            if found is None:continue
            score,x,y,w,h=found
            if score<500:continue
            # x/y text lines always sit just above the health bar, even if
            # partly white/occluded by the hat; do not segment by yellow alone.
            boxes=[(x+38,y-53,x+158,y-27),(x+38,y-25,x+158,y+1)]
            row={'trial':name,'frame':f,'time_s':f/60,'roll_input_frame':roll,
                 'anchor':[score,x,y,w,h],'lines':[]}
            for axis,(x1,y1,x2,y2) in zip(('x','y'),boxes):
                sub=frame[y1:y2,max(0,x1):min(frame.shape[1],x2)]
                texts.append(sub)
                row['lines'].append({'axis':axis,'box':[x1,y1,x2,y2]})
            crop=frame[max(0,y-65):min(frame.shape[0],y+65),max(0,x-10):min(frame.shape[1],x+170)]
            Image.fromarray(cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)).save(OUT/f'f{f:06d}.png')
            samples.append(row)
        print(name,'extracted',flush=True)
    cap.release()
    if preview_only:
        sheet=Image.new('RGB',(220*5,165*2),(25,25,25));d=ImageDraw.Draw(sheet)
        for i,row in enumerate(samples):
            x,y=i%5*220,i//5*165
            d.text((x,y),f"f{row['frame']} score{row['anchor'][0]}",fill='white')
            sheet.paste(Image.open(OUT/f"f{row['frame']:06d}.png"),(x,y+25))
        sheet.save(OUT/('launch_edges.png' if edges else 'anchor_check.png'))
        return
    ocr=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    refs=[(i,j) for i in range(len(samples)) for j in (0,1)]
    for start in range(0,len(texts),48):
        results,_=ocr.text_rec(texts[start:start+48])
        for (raw,confidence),(i,j) in zip(results,refs[start:start+48]):
            samples[i]['lines'][j].update(raw=raw,confidence=float(confidence))
        if start%192==0:print('OCR',start,'/',len(texts),flush=True)
    (OUT/'coordinates.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--preview',action='store_true');ap.add_argument('--edges',action='store_true');args=ap.parse_args()
    read_extract(args.preview or args.edges,args.edges)
