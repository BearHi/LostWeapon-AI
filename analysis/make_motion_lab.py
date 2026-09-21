"""One numbered, unobstructed LMF for recording motion, not certifying it."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'motion_lab'
NAME = '물리측정_통합01'
W, H, FLOOR = 252, 80, 73
SOURCE = Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF')
DIGITS = ['010111010010111', '111001111100111', '111001111001111',
          '101101111001001', '111100111001111', '111100111101111',
          '111001010010010', '111101111101111', '111101111001111']
TESTS = [
    ('일반 점프', '오른쪽', '↑만 눌렀다 떼기. 착지까지 다른 키 입력 없음.'),
    ('일반 점프＋이동', '오른쪽', '↑를 눌렀다 떼고, 발이 뜬 다음 →를 착지까지 유지. 구르기가 나오면 다시 시도.'),
    ('지상 뒷굴', '왼쪽', '지상에서 →＋↑로 뒷굴 발동 후 두 키 모두 떼기. 선행 점프 없음.'),
    ('점프＋뒷굴 / 키 해제', '왼쪽', '↑ 점프 후 ↑ 떼기 → 최고점 직전 →＋↑로 뒷굴 → 발동 즉시 두 키 모두 떼고 착지.'),
    ('점프＋뒷굴 / → 유지', '왼쪽', '4번과 같은 순서. 뒷굴 발동 후 ↑만 떼고 →는 착지까지 유지.'),
    ('점프＋앞굴 / 키 해제', '오른쪽', '↑ 점프 후 ↑ 떼기 → 최고점 직전 →＋↑로 앞굴 → 발동 즉시 두 키 모두 떼고 착지.'),
    ('점프＋앞굴 / → 유지', '오른쪽', '6번과 같은 순서. 앞굴 발동 후 ↑만 떼고 →는 착지까지 유지.'),
    ('점프＋낙하산', '오른쪽', '↑ 점프 후 ↑ 떼기 → 최고점 직전 C로 낙하산을 펴며 → 유지 → 착지까지 접지 않기.'),
    ('점프＋뒷굴＋낙하산', '왼쪽', '5번처럼 뒷굴 후 → 유지 → 뒷굴 뒤 상승이 끝날 무렵 C → 착지까지 → 유지, 낙하산 접지 않기.'),
]

def layout():
    cells = {(x,y): 8 for y in range(FLOOR,H) for x in range(W)}
    # All painted numbers are INSIDE existing solid floor, never in flight space.
    for i, glyph in enumerate(DIGITS):
        x = 14 + 22*i
        cells[x,FLOOR] = 7
        for j, v in enumerate(glyph):
            if v == '1': cells[x-1+j%3,FLOOR+1+j//3] = 7
    cells[14,FLOOR-2] = 100
    return cells

def manifest(cells):
    return {'name':NAME,'width':W,'height':H,'floor_y':FLOOR,
            'spawn':{'x':14,'y':FLOOR-2},'status':'unmeasured_motion_recording_fixture',
            'stations':[{'number':i+1,'x_marker':14+22*i,'action':t[0],
                         'facing':t[1],'input':t[2]} for i,t in enumerate(TESTS)],
            'tiles':[[tid,x,y] for (x,y),tid in sorted(cells.items())],
            'conditions':{'repeats':2,'rest_before_and_after_seconds':2,
                'record':'character-side coordinates and keyboard overlay, preferably 60 fps',
                'station_crossing':'Allowed: station markings are not obstacles or boundaries.',
                'parachute':'Do not close in flight; no cash-item-only sequence.',
                'timing_extra':'At station 4, additionally try one early airborne roll and one mid-ascent roll; retain all attempts in video.'}}

def preview(cells):
    scale=4; pad=30
    im=Image.new('RGB',(W*scale+60,490),'#171c24'); d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',17)
    small=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',13)
    d.text((pad,8),'물리측정 통합01 · 252 × 80칸 · 번호 사이 자유 이동',font=font,fill='#eeeeee')
    colors={8:'#806143',7:'#e6c99e',100:'#6fea99'}
    for (x,y),tid in cells.items():
        d.rectangle((pad+x*scale,40+y*scale,pad+(x+1)*scale-1,40+(y+1)*scale-1),fill=colors[tid])
    d.rectangle((pad,40,pad+W*scale-1,40+H*scale-1),outline='#626b77')
    for i in range(9):
        xx=pad+(14+22*i)*scale
        d.text((xx,312),str(i+1),anchor='mm',font=font,fill='#eeeeee')
        d.text((xx,370),f'{i+1}: x={14+22*i}',anchor='mm',font=small,fill='#eeeeee')
    d.text((pad,405),'바닥 위에는 암반·발판·천장·기믹 없음. 숫자와 출발 표시는 바닥에 있음.',font=font,fill='#eeeeee')
    d.text((pad,441),'앞/뒷굴의 발동 타이밍, 방향키를 뗀 궤적과 유지한 궤적, 낙하산 하강을 녹화하는 맵.',font=font,fill='#eeeeee')
    im.save(OUT/(NAME+'_미리보기.png'))

def validate_bytes(data,cells,source_header):
    w,h=struct.unpack_from('<HH',data,16); count=struct.unpack_from('<I',data,21)[0]
    assert (w,h)==(W,H) and len(data)==32+count*8
    records=[struct.unpack_from('<Ihh',data,32+i*8) for i in range(count)]
    decoded={(x,y):tid for tid,x,y in records}
    assert len(decoded)==count and decoded==cells
    assert all(0<=x<W and 0<=y<H for x,y in decoded)
    assert [r for r in records if r[0]==100]==[(100,14,FLOOR-2)]
    assert all(t in (7,8,100) for t in decoded.values())
    assert all(decoded.get((x,FLOOR)) in (7,8) for x in range(W))
    assert not any(t in (7,8) and y<FLOOR for (x,y),t in decoded.items())
    for s in range(9):
        x=14+22*s
        assert all(decoded.get((xx,yy)) not in (7,8) for xx in range(x-1,x+2) for yy in range(FLOOR-3,FLOOR))
    changed=set(range(16,20))|set(range(21,25))
    assert all(data[i]==source_header[i] for i in range(32) if i not in changed)
    return {'binary_roundtrip':True,'continuous_flat_floor':True,'all_starts_clear':True,
            'all_flight_space_clear':True,'records':count,'sha256':hashlib.sha256(data).hexdigest(),
            'game_loaded':False,'physics_simulated':False,'physical_maxima_measured':False}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--export',action='store_true'); args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    cells=layout(); m=manifest(cells)
    (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    preview(cells)
    if args.export:
        original=SOURCE.read_bytes()[:32]; assert len(original)==32
        header=bytearray(original)
        struct.pack_into('<HH',header,16,W,H); struct.pack_into('<I',header,21,len(cells))
        data=bytes(header)+b''.join(struct.pack('<Ihh',tid,x,y) for tid,x,y in m['tiles'])
        report=validate_bytes(data,cells,original)
        dest=ROOT/(NAME+'.LMF')
        if dest.exists() and dest.read_bytes()!=data: raise FileExistsError(dest)
        dest.write_bytes(data)
        validate_bytes(dest.read_bytes(),cells,original)
        (OUT/'structural_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    print(OUT/(NAME+'_미리보기.png'))

if __name__=='__main__': main()
