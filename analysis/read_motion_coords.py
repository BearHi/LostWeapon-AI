import sys,json,re,argparse,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2,numpy as np
from PIL import Image,ImageDraw
from rapidocr_onnxruntime import RapidOCR
OUT=Path(__file__).parent/'motion_075322'
def text_lines(im):
    r,g,b=im[:,:,0].astype(float),im[:,:,1].astype(float),im[:,:,2].astype(float)
    mask=((r>145)&(g>155)&(g>r*.94)&(b<155)&(g>b*1.6)).astype('uint8')*255
    mask[:140]=0;mask[260:]=0;mask[:,:30]=0;mask[:,195:]=0
    sums=(mask>0).sum(axis=1);active=sums>=8
    spans=[];s=None
    for y in range(len(active)+1):
        on=y<len(active) and active[y]
        if on and s is None:s=y
        if not on and s is not None:
            if y-s>=5:spans.append((s,y))
            s=None
    spans=[(a,b) for a,b in spans if 10<=b-a<=26]
    lines=[]
    for a,b in spans:
        xs=np.where((mask[a:b]>0).sum(axis=0)>0)[0]
        if not len(xs):continue
        x1,x2=max(0,xs.min()-3),min(im.shape[1],xs.max()+4)
        if x2-x1<55:continue
        region=im[max(0,a-3):b+3,x1:x2]
        lines.append((a,region,mask[max(0,a-3):b+3,x1:x2]))
    return lines
def main():
    p=argparse.ArgumentParser();p.add_argument('--stride',type=int,default=30);p.add_argument('--limit',type=int,default=0);p.add_argument('--suffix',default='sample');p.add_argument('--from-frame',type=int,default=0);a=p.parse_args()
    o=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    files=[f for f in sorted((OUT/'crops').glob('f*.png')) if int(f.stem[1:])%a.stride==0 and int(f.stem[1:])>=a.from_frame]
    if a.limit:files=files[:a.limit]
    rows=[];all_lines=[];indices=[]
    for f in files:
        im=np.array(Image.open(f));ls=text_lines(im)
        row={'frame':int(f.stem[1:]),'lines':[]};rows.append(row)
        for y,reg,mask in ls:
            all_lines.append(cv2.cvtColor(reg,cv2.COLOR_RGB2BGR));indices.append((len(rows)-1,y))
    for start in range(0,len(all_lines),48):
        results,elapsed=o.text_rec(all_lines[start:start+48])
        for result,(rowid,y) in zip(results,indices[start:start+48]):
            rows[rowid]['lines'].append({'y':y,'raw':result[0],'confidence':float(result[1])})
        print('read',min(start+48,len(all_lines)),'/',len(all_lines),flush=True)
        (OUT/f'ocr_{a.suffix}_partial.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    (OUT/f'ocr_{a.suffix}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(rows[:12],ensure_ascii=True),flush=True)
if __name__=='__main__':main()
