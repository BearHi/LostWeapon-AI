"""Extract timestamped source frames; no coordinate inference in this step."""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import cv2
from PIL import Image, ImageDraw

def main():
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('--step',type=float,default=5);p.add_argument('--start',type=float,default=0);p.add_argument('--end',type=float);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(a.video); assert cap.isOpened()
    fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));w=int(cap.get(3));h=int(cap.get(4))
    meta={'source':a.video,'fps':fps,'frames':n,'width':w,'height':h,'duration_s':n/fps}
    (out/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print(meta)
    stamps=[];t=a.start
    while t<min(a.end if a.end is not None else n/fps,n/fps):
        frame=round(t*fps);cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,bgr=cap.read()
        if not ok:break
        im=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB));im.save(out/f'f{frame:06d}.jpg',quality=95)
        im.thumbnail((256,384));thumb=Image.new('RGB',(256,412),'#222222');thumb.paste(im,(0,28));ImageDraw.Draw(thumb).text((5,7),f'{frame/fps:.3f}s  frame {frame}',fill='white');stamps.append(thumb);t+=a.step
    for offset in range(0,len(stamps),20):
        batch=stamps[offset:offset+20];sheet=Image.new('RGB',(256*5,412*((len(batch)+4)//5)),'#222222')
        for i,im in enumerate(batch):sheet.paste(im,(i%5*256,i//5*412))
        sheet.save(out/f'contact_{offset//20:02d}.jpg',quality=92)
    cap.release()
if __name__=='__main__':main()
