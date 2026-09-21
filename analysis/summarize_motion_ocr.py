import json,re,math
from pathlib import Path
import numpy as np
OUT=Path(__file__).parent/'motion_075322'
def parse(raw,axis):
    s=raw.replace(' ','').replace(',', '.')
    # Preserve original OCR. Only an explicit separator is accepted here.
    m=re.fullmatch(r'(\d{1,3}):(-?\d{1,2}\.\d{3})',s)
    if not m:return None
    cell=int(m[1]);offset=float(m[2])
    if not 0<=offset<32:return None
    if axis=='y' and not 50<=cell<=74:return None
    if axis=='x' and not 0<=cell<=251:return None
    return {'cell':cell,'offset':offset,'tiles':cell+offset/32}
def main():
    by={}
    for name in ['ocr_dense.json','ocr_tail_partial.json','ocr_tail.json']:
        p=OUT/name
        if not p.exists():continue
        for row in json.loads(p.read_text(encoding='utf-8')):
            if len(row['lines'])!=2:continue
            ls=sorted(row['lines'],key=lambda l:l['y'])
            x=parse(ls[0]['raw'],'x');y=parse(ls[1]['raw'],'y')
            q={'frame':row['frame'],'time_s':row['frame']/60,'raw_x':ls[0]['raw'],'raw_y':ls[1]['raw'],
               'x':x,'y':y,'confidence':min(l['confidence'] for l in ls)}
            if row['frame'] not in by or q['confidence']>by[row['frame']]['confidence']:by[row['frame']]=q
    rows=sorted(by.values(),key=lambda r:r['frame'])
    (OUT/'coordinate_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    keys=json.loads((OUT/'keys.json').read_text())
    starts=[i for i in range(1,len(keys)) if keys[i]['up'] and not keys[i-1]['up']]
    summaries=[]
    for f in starts:
        rs=[r for r in rows if f-9<=r['frame']<=f+180 and r['y'] and r['confidence']>.92]
        if not rs:continue
        best=min(rs,key=lambda r:r['y']['tiles'])
        summaries.append({'up_time':round(f/60,3),'min_y_time':best['time_s'],'raw_x':best['raw_x'],'raw_y':best['raw_y'],'height':round(73-best['y']['tiles'],4)})
    (OUT/'jump_candidates.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')
    print('rows',len(rows));print(json.dumps(summaries,ensure_ascii=True))
if __name__=='__main__':main()
