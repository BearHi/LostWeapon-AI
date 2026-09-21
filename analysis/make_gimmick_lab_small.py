"""Compact single-magnet observation fixture; preview before --export.

Only one force source: position dependence is observed, not pre-calculated.
Raster preview uses the actual extracted editor bitmaps, not generic dots.
"""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'gimmick_lab_small'
NAME = '물리측정_간단03'
W, H, FLOOR = 72, 56, 48
MAGNET_ID, MAGNET_XY = 0x37, (20, 43)
SOURCE = Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF')
GAME = SOURCE.parent


def layout():
    cells = {(x,y):8 for y in range(FLOOR,H) for x in range(W)}
    cells[6,46] = 100
    cells[MAGNET_XY] = MAGNET_ID
    # Eight-cell icy descent. Ladder gives repeatable access to the left lip.
    for x in range(44,48):
        for y in range(40,FLOOR): cells[x,y] = 8
    for i in range(8):
        x,y = 48+i,40+i
        cells[x,y] = 0x25
        for yy in range(y+1,FLOOR): cells[x,yy] = 8
    for y in range(39,FLOOR): cells[42,y] = 3
    glyphs = ['010110010010111','111001111100111','111001111001111']
    for x,glyph in zip((12,20,48),glyphs):
        cells[x,48] = 7
        for j,v in enumerate(glyph):
            if v=='1': cells[x-1+j%3,49+j//3] = 7
    return cells


def font(n): return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',n)


def preview(cells):
    mapping = json.loads((ROOT/'analysis'/'tilemap.json').read_text(encoding='utf-8'))
    # Full map overview plus a large lower-half crop. Sky is not an obstacle.
    im = Image.new('RGB',(1200,560),'#17212a')
    draw = ImageDraw.Draw(im)
    draw.text((24,16),'간단03 · 자석 하나 + 얼음 경사 · 72 × 56칸',font=font(24),fill='#edf1f4')
    draw.text((24,52),'1·2: 같은 점프 비교     3: 미끄러진 뒤 점프',font=font(18),fill='#ccd9e3')
    assets = {}
    for tid in set(cells.values()):
        assets[tid] = Image.open(ROOT/'analysis'/f'bitmap_{mapping[str(tid)]}.bmp').convert('RGB')
    # Actual tile artwork keeps magnets recognizable. Magenta is transparency.
    for (x,y),tid in cells.items():
        if y < 30: continue
        tile = assets[tid].resize((16,16),Image.Resampling.NEAREST)
        mask = tile.convert('L').point(lambda _:255)
        mask.putdata([0 if r>220 and g<50 and b>220 else 255 for r,g,b in tile.getdata()])
        im.paste(tile,(24+x*16,108+(y-30)*16),mask)
    for x,label in [(12,'1 · 옆'),(20,'2 · 바로 아래')]:
        px=24+x*16
        draw.text((px,345),label,font=font(15),fill='#ffffff',anchor='mm')
    draw.text((24+20*16,289),'자석 1개',font=font(17),fill='#ffd378',anchor='mm')
    draw.text((24+48*16,222),'3 · 얼음 경사',font=font(17),fill='#b5ebff')
    draw.text((24+40*16,280),'사다리',font=font(14),fill='#dfc5ed',anchor='rm')
    draw.text((24,535),'바닥에서 자석 밑면까지 빈 공간 4칸. 위쪽 빈 공간은 생략한 확대도.',font=font(15),fill='#ccd9e3')
    im.save(OUT/f'{NAME}_미리보기.png')
    mini=Image.new('RGB',(W,H),'#17212a')
    palette={8:'#826348',7:'#ebdb9d',100:'#6ef797',55:'#ffcd59',37:'#8cdcfa',3:'#cc8ce6'}
    for (x,y),tid in cells.items(): mini.putpixel((x,y),tuple(bytes.fromhex(palette[tid][1:])))
    mini.resize((W*5,H*5),Image.Resampling.NEAREST).save(OUT/f'{NAME}_전체도트.png')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--export',action='store_true')
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    cells=layout()
    counts=Counter(cells.values())
    assert sum(counts[t] for t in (52,53,54,55))==1
    assert counts[37]==8 and counts[100]==1
    assert cells[MAGNET_XY]==55
    assert all((20,y) not in cells for y in range(44,48))
    assert all(0<=x<W and 0<=y<H for x,y in cells)
    assert all(cells[42,y]==3 for y in range(39,48))
    assert all(cells[x,48] in (7,8) for x in range(W))
    assert all((x,y) not in cells for x in range(8,60) for y in range(0,38))
    preview(cells)
    report={'name':NAME,'dimensions':[W,H],'tile_counts_decimal':dict(counts),
            'magnet':{'editor_label':'37','lmf_id':55,'position':list(MAGNET_XY),'empty_cells_below':4},
            'tests':[{'number':1,'x':12,'instruction':'3초 앉았다가 점프+뒷굴 2회'},
                     {'number':2,'x':20,'instruction':'1번과 같은 방향/입력으로 3초 앉았다 점프+뒷굴 2회'},
                     {'number':3,'x':48,'instruction':'사다리로 올라가 얼음 경사를 오른쪽으로 미끄러지다 점프+뒷굴 2회'}],
            'user_observations':['magnet position and distance change effective gravity/jump',
                                 'floor-level upward magnet only slightly increases jump',
                                 'multiple magnets combine forces; excluded this pass'],
            'analysis_limits':['position trials use the same dwell time and action',
                               'ice trial is observational: influence from the lone magnet is not ruled out',
                               'object contact or map-edge clipped flights must be flagged',
                               'do not fit a certified physics model from these six trials alone'],
            'checks':{'in_bounds':True,'magnet_count_one':True,'magnet_not_buried':True,
                      'continuous_floor':True,'ice_ladder_present':True,'game_tested':False}}
    if args.export:
        original=SOURCE.read_bytes()[:32]
        assert len(original)==32
        header=bytearray(original)
        records=[(tid,x,y) for (x,y),tid in sorted(cells.items(),key=lambda v:(v[0][1],v[0][0]))]
        struct.pack_into('<HH',header,16,W,H)
        struct.pack_into('<I',header,21,len(records))
        data=bytes(header)+b''.join(struct.pack('<Ihh',*r) for r in records)
        assert len(data)==32+len(records)*8
        assert [struct.unpack_from('<Ihh',data,32+8*i) for i in range(len(records))]==records
        changed=set(range(16,20))|set(range(21,25))
        assert all(data[i]==original[i] for i in range(32) if i not in changed)
        for folder in (ROOT,GAME):
            dest=folder/f'{NAME}.LMF'
            if dest.exists() and dest.read_bytes()!=data: raise FileExistsError(dest)
            dest.write_bytes(data)
            assert dest.read_bytes()==data
            print(dest)
        report['checks']['binary_roundtrip']=True
        report['sha256']=hashlib.sha256(data).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(OUT/f'{NAME}_미리보기.png')


if __name__=='__main__': main()
