"""Publish visually checked traces and clearly bounded prediction results."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from verified_gimmick_samples import verified

OUT=Path(__file__).parent/'motion_180606'/'refined'
CASES={
 'M3':{'name':'자석 아래','ground_frame':816,'ground_y':48,'pre_end':864,'end':912},
 'I1':{'name':'얼음 통과 후 평지','ground_frame':1917,'ground_y':48,'pre_end':1962,'end':2025},
 'I2':{'name':'경사 중간 이륙','ground_frame':2464,'ground_y':45+4/32,'pre_end':2520,'end':2574},
 'I3':{'name':'경사 끝 이륙','ground_frame':2873,'ground_y':47+22/32,'pre_end':2931,'end':2997},
 'I4':{'name':'후속 평지 점프','ground_frame':3052,'ground_y':48,'pre_end':3096,'end':3153},
}


def main():
    samples=verified()
    cases={}
    for name,c in CASES.items():
        pts=[{'frame':f,'time_s':(f-c['ground_frame'])/60,'y':v['y'],
              'height':c['ground_y']-v['y'],'raw_y':v['raw_y']}
             for f,v in samples.items() if v['trial']==name and c['ground_frame']<f<=c['end']]
        pre=[p for p in pts if p['frame']<=c['pre_end']]
        cases[name]={**c,'time_basis':'last observed surface contact frame; video sampling uncertainty remains',
                     'pre_roll_peak':max(pre,key=lambda p:p['height']),
                     'whole_peak':max(pts,key=lambda p:p['height']),'points':pts}
    (OUT/'observed_motion_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',n)
    im=Image.new('RGB',(1120,730),'#fafafa');d=ImageDraw.Draw(im)
    d.text((34,18),'실제 영상 좌표 · 이륙 지점에서 얼마나 올라갔나',font=font(24),fill='#19212b')
    d.text((34,55),'점은 확인한 좌표, 선은 점 사이 연결. 게임 물리 시뮬레이션 결과가 아님.',font=font(16),fill='#555d65')
    x0,y0,pw,ph=94,120,960,420
    px=lambda t:x0+t/2.1*pw
    py=lambda h:y0+ph-h/18*ph
    for h in range(0,19,3):
        y=py(h);d.line((x0,y,x0+pw,y),fill='#d7dce1')
        d.text((x0-12,y),str(h),font=font(16),fill='#27303a',anchor='rm')
    for t in (0,.5,1,1.5,2):
        x=px(t);d.line((x,y0,x,y0+ph),fill='#e1e4e8')
        d.text((x,y0+ph+8),str(t),font=font(16),fill='#27303a',anchor='mt')
    d.text((15,95),'상승량(칸)',font=font(16),fill='#27303a')
    d.text((510,581),'이륙 직전 기준 경과시간(초)',font=font(16),fill='#27303a')
    palette={'M3':'#737b83','I1':'#ba5825','I2':'#3265ad','I3':'#257d63','I4':'#884ea2'}
    for i,(name,c) in enumerate(cases.items()):
        color=palette[name]
        points=[(px(0),py(0))]+[(px(p['time_s']),py(p['height'])) for p in c['points'] if 0<=p['time_s']<=2.1 and 0<=p['height']<=18]
        d.line(points,fill=color,width=2)
        for x,y in points:d.ellipse((x-2,y-2,x+2,y+2),fill=color)
        peak=c['whole_peak'];x,y=px(peak['time_s']),py(peak['height'])
        d.ellipse((x-5,y-5,x+5,y+5),fill=color)
        lx,ly=34+(i%3)*365,625+(i//3)*35
        d.line((lx,ly+10,lx+25,ly+10),fill=color,width=3)
        d.text((lx+33,ly),f"{name} {c['name']} · {peak['height']:.2f}칸",font=font(15),fill='#26303a')
    d.text((34,704),'구르기 시점은 시도마다 다름. 이 관측값을 모든 맵의 최대 점프력으로 사용하지 않음.',font=font(14),fill='#555d65')
    im.save(OUT/'측정궤적_비교.png')
    for name,c in cases.items():
        print(name,c['ground_y'],c['pre_roll_peak']['height'],c['whole_peak']['height'])


if __name__=='__main__':main()
