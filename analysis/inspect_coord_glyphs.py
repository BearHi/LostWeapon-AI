import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2,numpy as np
from PIL import Image,ImageDraw
from read_motion_coords import text_lines,OUT
def spans(a):
    start=None;out=[]
    for i in range(len(a)+1):
        on=i<len(a) and a[i]
        if on and start is None:start=i
        if not on and start is not None:out.append((start,i));start=None
    return out
def split(mask):
    # Disconnected colon dots share an x range and remain one glyph.
    return [(a,b,mask[:,a:b]) for a,b in spans((mask>0).sum(axis=0)>0)]
if __name__=='__main__':
    rows=json.loads((OUT/'ocr_sample.json').read_text(encoding='utf-8'))
    sheet=Image.new('RGB',(1000,80*len(rows)),(25,25,25));d=ImageDraw.Draw(sheet)
    for n,row in enumerate(rows):
        im=np.array(Image.open(OUT/'crops'/f'f{row["frame"]:06d}.png'));ls=text_lines(im)
        d.text((5,n*80+3),str(row['frame'])+' '+str([l['raw'] for l in row['lines']]),fill='white')
        x=400
        for yy,reg,mask in ls:
            sheet.paste(Image.fromarray(mask).resize((mask.shape[1]*2,mask.shape[0]*2)),(x,n*80+5))
            for a,b,g in split(mask):d.line((x+2*a,n*80,x+2*a,n*80+65),fill='red')
            x+=300
    sheet.save(OUT/'glyphs.png')
