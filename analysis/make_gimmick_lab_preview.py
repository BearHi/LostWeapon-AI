"""One-file physics lab. Editor labels are HEX, LMF IDs are integers.

Preview first, then --export. Dynamics and magnetic isolation are unmeasured.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'gimmick_lab'
NAME = '물리측정_기믹통합02'
SOURCE = Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF')
W, H = 160, 600
DIGITS = ['010110010010111', '111001111100111', '111001111001111',
          '101101111001001', '111100111001111', '111100111101111',
          '111001010010010', '111101111101111', '111101111001111']
ROOMS = [
    ('평지 기준', 'flat', None),
    ('가로 자석 · 에디터 36', 'magnet', 0x36),
    ('가로 자석 · 에디터 37', 'magnet', 0x37),
    ('평면 얼음 · 에디터 13', 'ice', 0x13),
    ('일반 내리막 · 에디터 20', 'slope', 0x20),
    ('삼각 얼음 내리막 · 에디터 25', 'slope', 0x25),
    ('세로 자석 · 에디터 34', 'magnet', 0x34),
    ('세로 자석 · 에디터 35', 'magnet', 0x35),
    ('선풍기 · 에디터 33', 'fan', 0x33),
]


def layout():
    cells = {}
    def box(x1, y1, x2, y2, tid=8):
        for y in range(y1, y2+1):
            for x in range(x1, x2+1):
                cells[x,y] = tid
    box(0,0,0,H-1)
    box(W-1,0,W-1,H-1)
    box(0,H-2,W-1,H-1)
    box(4,60,4,H-3,3)
    rooms = []
    for i,(title,kind,tid) in enumerate(ROOMS):
        floor = 576-64*i
        box(8,floor,W-2,floor+6)
        for j,bit in enumerate(DIGITS[i]):
            if bit=='1': cells[12+j%3,floor+1+j//3]=7
        for x in (40,56,64,72,80,88,104): cells[x,floor+6]=7
        if kind in ('magnet','fan'):
            cells[72,floor-1]=tid
        elif kind=='ice':
            box(40,floor,104,floor,tid)
        elif kind=='slope':
            box(8,floor-12,51,floor-1)
            for n in range(12):
                x,y=52+n,floor-12+n
                cells[x,y]=tid
                box(x,y+1,x,floor-1)
        rooms.append({'number':i+1,'title':title,'kind':kind,'floor_y':floor,
                      'lmf_id':tid,'editor_hex':None if tid is None else f'{tid:02X}',
                      'object_xy':[72,floor-1] if kind in ('magnet','fan') else None})
    cells[16,574]=100
    return cells,rooms


def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',size)


def render(cells,rooms):
    im=Image.new('RGB',(1140,860),'#151b23')
    d=ImageDraw.Draw(im)
    colors={8:'#826348',7:'#efd5a5',3:'#bc79cd',100:'#75e7a2',19:'#7cd5ed',
            32:'#c88870',37:'#7cd5ed',52:'#efbc54',53:'#efbc54',54:'#efbc54',55:'#efbc54',51:'#8faaf0'}
    d.text((24,16),'기믹 통합02 · 9개 측정실 / 아래 1번부터 위로',font=font(24),fill='#edf0f5')
    d.text((24,53),'실제 타일 배치 · 실제 운동은 촬영 후 측정 · 오른쪽은 각 방 바닥 부근 확대',font=font(15),fill='#bec9d4')
    ox,oy=26,99
    for (x,y),tid in cells.items(): d.point((ox+x,oy+y),fill=colors.get(tid,'#aaaaaa'))
    for r in rooms: d.text((193,oy+r['floor_y']-14),str(r['number']),font=font(16),fill='#edf0f5')
    d.text((24,718),'160 × 600칸',font=font(17),fill='#edf0f5')
    d.text((24,747),'왼쪽: 이동용 사다리',font=font(13),fill='#c0cad4')
    d.text((24,770),'측정은 방 안에서 진행',font=font(13),fill='#c0cad4')
    for i,r in enumerate(rooms):
        px,py,s=285,94+i*81,5
        d.text((px,py),f"{r['number']}  {r['title']}    바닥 y={r['floor_y']}",font=font(15),fill='#edf0f5')
        for (x,y),tid in cells.items():
            if r['floor_y']-13<=y<=r['floor_y']+1:
                xx,yy=px+x*s,py+23+(y-r['floor_y']+13)*3
                if tid in (32,37): d.polygon([(xx,yy),(xx,yy+2),(xx+4,yy+2)],fill=colors[tid])
                else: d.rectangle((xx,yy,xx+4,yy+2),fill=colors.get(tid,'#aaaaaa'))
        if r['object_xy']: d.text((px+72*s+10,py+32),'x=72',font=font(12),fill='#edf0f5')
    im.save(OUT/f'{NAME}_미리보기.png')


def tile_sheet():
    mapping=json.loads((ROOT/'analysis'/'tilemap.json').read_text(encoding='utf-8'))
    im=Image.new('RGB',(1000,250),'#e7e7e7')
    d=ImageDraw.Draw(im)
    d.text((14,8),'에디터 표시(16진수)와 LMF 저장값(10진수) 대조',font=font(20),fill='#18212b')
    for i,tid in enumerate([19,27,37,32,51,52,53,54,55,82]):
        asset=mapping[str(tid)]
        pic=Image.open(ROOT/'analysis'/f'bitmap_{asset}.bmp').convert('RGB')
        im.paste(pic.resize((56,56),Image.Resampling.NEAREST),(i*100+15,57))
        for y,txt in [(125,f'표시 {tid:02X}'),(149,f'LMF {tid}'),(175,f'asset {asset}')]:
            d.text((i*100+15,y),txt,font=font(14),fill='#18212b')
    d.text((14,213),'그림 확인 자료. 힘의 크기·접촉 판정·높이 증가 원인은 아직 실측 전.',font=font(15),fill='#18212b')
    im.save(OUT/'타일번호_16진수_대조.png')


def check(cells,rooms):
    assert all(0<=x<W and 0<=y<H for x,y in cells)
    assert sum(t==100 for t in cells.values())==1
    assert all(cells[4,y]==3 for y in range(60,H-2))
    for r in rooms:
        f=r['floor_y']
        assert all(cells[x,f+1] in (7,8) for x in range(8,W-1))
        assert all(cells.get((x,f-2)) in (None,3) for x in range(2,8))
        assert all((x,y) not in cells for x in range(64,125) for y in range(f-45,f-2))
    return {'bounds':True,'continuous_access_ladder':True,'supported_room_floors':True,
            'launch_region_45_cells_clear':True,'game_tested':False,
            'gimmick_physics_calibrated':False,'magnet_field_isolation_verified':False}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--export',action='store_true')
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    cells,rooms=layout()
    checks=check(cells,rooms)
    render(cells,rooms)
    tile_sheet()
    manifest={'name':NAME,'width':W,'height':H,'rooms':rooms,
              'tile_numbering':'editor HEX / LMF integer decimal','checks':checks,
              'physics_status':'measurement_fixture_only',
              'magnet_note':'64-cell spacing is not proof of field isolation. Compare room 1 with pure lab and return baseline.',
              'hypotheses':['jump launch velocity changes','effective gravity changes',
                            'contact/sliding preserves or converts velocity','hidden state persists after leaving'],
              'measure':['actual input frame','character-side raw coordinates','takeoff and apex',
                         'ascent duration','early vertical speed','descent speed','horizontal displacement',
                         'standing/crouched posture','contact duration','leave-and-retest behavior']}
    if args.export:
        original=SOURCE.read_bytes()[:32]
        assert len(original)==32
        header=bytearray(original)
        records=[(tid,x,y) for (x,y),tid in sorted(cells.items(),key=lambda p:(p[0][1],p[0][0]))]
        struct.pack_into('<HH',header,16,W,H)
        struct.pack_into('<I',header,21,len(records))
        data=bytes(header)+b''.join(struct.pack('<Ihh',*r) for r in records)
        changed=set(range(16,20))|set(range(21,25))
        assert all(data[i]==original[i] for i in range(32) if i not in changed)
        assert len(data)==32+len(records)*8
        assert [struct.unpack_from('<Ihh',data,32+i*8) for i in range(len(records))]==records
        dest=ROOT/(NAME+'.LMF')
        if dest.exists() and dest.read_bytes()!=data: raise FileExistsError(dest)
        dest.write_bytes(data)
        assert dest.read_bytes()==data
        checks.update(binary_roundtrip=True,records=len(records),sha256=hashlib.sha256(data).hexdigest())
        print(dest)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'structural_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(OUT/f'{NAME}_미리보기.png')


if __name__=='__main__': main()
