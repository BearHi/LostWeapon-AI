"""Compact ice + paired near-field magnet fixtures; preview before export.

Count comparison preserves the first source and adds one adjacent source.
Never claims equal distance to both sources or proven cross-fixture isolation.
"""
import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'/'video_runtime'))
from PIL import Image,ImageDraw,ImageFont

OUT=ROOT/'analysis'/'compact_magnet05'
NAME='물리측정_압축05'
SOURCE=Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF')
W,H=72,118
ROWS=[(110,55,'37'),(84,52,'34'),(58,53,'35')]
DIGITS=['010110010010111','111001111100111','111001111001111',
        '101101111001001','111100111101111','111100111001111','111001010010010']
# Keep numerals 5 and 6 conventional below.
DIGITS[4]='111100111001111';DIGITS[5]='111100111101111'


def build():
    c={};stations=[]
    def box(x1,y1,x2,y2,t=8):
        for y in range(y1,y2+1):
            for x in range(x1,x2+1):
                assert 0<=x<W and 0<=y<H
                c[x,y]=t
    box(0,0,0,H-1);box(71,0,71,H-1);box(0,116,71,117)
    for f,_,_ in ROWS:
        box(8,f,32,f+1);box(39,f,65,f+1)
    box(8,32,65,33)
    for x in (4,35,36,68):
        for y in range(5,116):
            if y in (32,33) and x in (35,36):continue
            c[x,y]=3
    c[10,108]=100
    for row,(f,tid,label) in enumerate(ROWS):
        for col,count in enumerate((1,2)):
            xshift=32*col
            source=(17+xshift,f-(1 if tid==55 else 3))
            magnets=[source]+([(source[0]-1,source[1])] if count==2 else [])
            for p in magnets:
                assert p not in c;c[p]=tid
            marks=[(source[0]+d,f) for d in ((1,2,3) if tid==55 else (0,1,2))]
            for j,p in enumerate(marks):c[p]=7 if j!=1 else 8
            # Three floor marks with a bright baseline underneath: 7/8/7
            # remains visible; coordinates, not paint width, define trials.
            for x,_ in marks:c[x,f+1]=7
            number=row*2+col+1
            for k,v in enumerate(DIGITS[number-1]):
                if v=='1':c[9+xshift+k%3,f-21+k//3]=7
            stations.append({'number':number,'floor_y':f,'column':col,'editor_hex':label,
                'id_decimal':tid,'count':count,'magnets':[list(p) for p in magnets],
                'marks':[{'step':i,'floor_reference':list(p),
                          'tile_index_dx_dy_from_primary':[p[0]-source[0],p[1]-source[1]]}
                         for i,p in enumerate(marks)],
                'empty_cells_below_primary':f-source[1]-1,
                'instruction':'오른쪽을 보고 표시 3곳에서 각각 약 2초 앉았다 일반 점프. 구르기·C 없이.',
                'distance_note':'표시는 바닥 좌표. 캐릭터 중심/몸 끝까지의 실제 거리는 영상으로 판독.',
                'count_note':'첫 자석 위치를 유지하고 그 왼쪽에 1개 추가; 두 자석까지의 거리는 같지 않음.'})
    # Ice is the only remaining non-magnet experiment, in open top sky.
    box(13,24,17,31);box(11,23,11,31,3)
    for j in range(8):
        c[18+j,24+j]=37
        box(18+j,25+j,18+j,31)
    for x in (28,40,52):c[x,32]=7
    for k,v in enumerate(DIGITS[6]):
        if v=='1':c[9+k%3,5+k//3]=7
    stations.append({'number':7,'floor_y':32,'column':None,'kind':'ice',
                     'slope':{'id_decimal':37,'length':8,'start':[18,24]},
                     'runway_x':[26,65],
                     'instruction':'사다리로 올라가 얼음 중간/끝에서 점프+뒷굴. 내려와 평지에서 한 번 더 점프.'})
    return c,stations


def validate(c,stations):
    assert len(stations)==7
    cnt=Counter(c.values())
    assert cnt[100]==1 and all(cnt[t]==3 for t in (52,53,55))
    assert cnt[37]==8
    assert not any(t in cnt for t in (4,22,49,51,54,82,86,119,122))
    assert all(0<=x<W and 0<=y<H for x,y in c)
    for x in (4,68):assert all(c[x,y]==3 for y in range(5,116))
    for s in stations[:6]:
        f=s['floor_y']
        for mark in s['marks']:
            x,y=mark['floor_reference']
            assert c[x,y] in (7,8)
            assert all(c.get((x,yy)) not in (7,8) for yy in range(f-16,f))
        for x,y in s['magnets']:
            assert c[x,y]==s['id_decimal']
            assert all((x,yy) not in c for yy in range(y+1,f))
    for a,b in zip(stations[0:6:2],stations[1:6:2]):
        assert a['count']==1 and b['count']==2 and a['floor_y']==b['floor_y']
        assert b['magnets'][0]==[a['magnets'][0][0]+32,a['magnets'][0][1]]
        assert b['magnets'][1]==[b['magnets'][0][0]-1,b['magnets'][0][1]]
        assert [m['tile_index_dx_dy_from_primary'] for m in a['marks']]==[m['tile_index_dx_dy_from_primary'] for m in b['marks']]
    # Exact distances to *other fixtures* recorded, not asserted inactive.
    distances=[]
    for s in stations[:6]:
        for m in s['marks']:
            x,y=m['floor_reference']
            other=[((x-mx)**2+(y-my)**2)**.5 for t in stations[:6]
                   if t['number']!=s['number'] for mx,my in t['magnets']]
            distances.append({'station':s['number'],'step':m['step'],
                              'nearest_other_fixture_from_floor_reference':min(other)})
    return {'in_bounds':True,'unique_spawn':True,'continuous_outer_ladders':True,
            'one_vs_two_primary_source_and_marks_match':True,
            'standing_marks_no_rock_for_16_cells_above':True,
            'source_not_embedded_in_floor':True,'tile_counts_decimal':dict(cnt),
            'cross_fixture_distances_cells':distances,
            'cross_fixture_isolation_verified':False,'game_tested':False,
            'force_law_fitted':False,'engine_clear_certified':False}


def font(n):return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',n)


def preview(c,stations):
    palette={7:'#ead89f',8:'#91714e',3:'#c294e5',100:'#65eca6',37:'#83dced',52:'#ffbf63',53:'#ffbf63',55:'#ffbf63'}
    mini=Image.new('RGB',(W,H),'#172531')
    for p,t in c.items():mini.putpixel(p,tuple(bytes.fromhex(palette[t][1:])))
    mini.resize((W*6,H*6),Image.Resampling.NEAREST).save(OUT/f'{NAME}_전체도트.png')
    im=Image.new('RGB',(940,1060),'#172531');d=ImageDraw.Draw(im)
    d.text((20,15),'압축05 · 얼음 + 자석만',font=font(27),fill='#f2f4f7')
    d.text((20,55),'72 × 118칸 · 이전 면적의 27% · 아래 1·2 → 3·4 → 5·6 → 얼음 7',font=font(17),fill='#cfdae3')
    im.paste(mini.resize((576,944),Image.Resampling.NEAREST),(20,92))
    for row,(f,_,label) in enumerate(ROWS):
        yy=92+(f-21)*8
        d.text((20+14*8,yy),f'자석 {label} · 1개',font=font(14),fill='#f2f4f7')
        d.text((20+46*8,yy),f'자석 {label} · 2개',font=font(14),fill='#f2f4f7')
    d.text((20+16*8,92+5*8),'얼음 8칸 경사',font=font(16),fill='#f2f4f7')
    mapping=json.loads((ROOT/'analysis'/'tilemap.json').read_text(encoding='utf-8'))
    for t in (52,53,55):
        asset=Image.open(ROOT/'analysis'/f'bitmap_{mapping[str(t)]}.bmp').convert('RGB').resize((16,16),Image.Resampling.NEAREST)
        mask=Image.new('L',(16,16));mask.putdata([0 if r>220 and g<50 and b>220 else 255 for r,g,b in asset.getdata()])
        # Overview is exactly one tile per dot: use actual-size sprite inset
        # on the right to make orientation legible without changing dot map.
        yy={55:150,52:216,53:282}[t]
        im.paste(asset.resize((40,40),Image.Resampling.NEAREST),(624,yy),mask.resize((40,40),Image.Resampling.NEAREST))
        d.text((678,yy+7),f'에디터 {t:02X}',font=font(18),fill='#f2f4f7')
    lines=[(350,'자석: 같은 조작으로 비교'),(384,'① 가까운 표시부터'),(412,'② 한 칸씩 옆으로 이동'),
           (440,'③ 각각 잠깐 앉았다 점프'),(486,'구르기 / C는 쓰지 않기'),
           (538,'왼쪽: 1개'),(566,'오른쪽: 기존 위치 + 1개'),
           (614,'세로 자석: 바로 아래부터'),(642,'가로 자석: 바로 옆부터'),
           (700,'얼음만 점프 + 뒷굴'),(750,'부딪힌 시도는 따로 기록'),(798,'자석 간섭 범위는 미검증')]
    for yy,line in lines:d.text((624,yy),line,font=font(17),fill='#cfdae3')
    im.save(OUT/f'{NAME}_미리보기.png')
    # Full-resolution actual tile artwork, useful for auditing close placement.
    detail=Image.new('RGB',(W*16,H*16),'#172531')
    for t in set(c.values()):
        tile=Image.open(ROOT/'analysis'/f'bitmap_{mapping[str(t)]}.bmp').convert('RGB').resize((16,16),Image.Resampling.NEAREST)
        mask=Image.new('L',tile.size);mask.putdata([0 if r>220 and g<50 and b>220 else 255 for r,g,b in tile.getdata()])
        for (x,y),tid in c.items():
            if tid==t:detail.paste(tile,(x*16,y*16),mask)
    detail.save(OUT/f'{NAME}_실제타일.png')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--export',action='store_true');args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    c,s=build();checks=validate(c,s)
    digest=hashlib.sha256(json.dumps(sorted((x,y,t) for (x,y),t in c.items())).encode()).hexdigest()
    report={'name':NAME,'width':W,'height':H,'area_ratio_to_lab04':W*H/(200*160),
            'layout_sha256':digest,'stations':s,'checks':checks,
            'comparison_limits':['Count comparison adds one source at x-1, not an equal-distance abstract force multiplier.',
                                 'Direction 36 is deferred; no symmetry with 37 is assumed.',
                                 'Other fixtures are distant but their force range is not measured.',
                                 'Compare actual pre-jump pose/coordinates, not floor marks alone.',
                                 'Two-second crouch is a common input condition, not a proven saturation time.',
                                 'Ceiling and map-edge contacts censor flight extrema.']}
    if not args.export:
        preview(c,s)
        (OUT/'preview_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        assert json.loads((OUT/'preview_manifest.json').read_text(encoding='utf-8'))['layout_sha256']==digest
        src=SOURCE.read_bytes();head=bytearray(src[:32])
        struct.pack_into('<HH',head,16,W,H);struct.pack_into('<I',head,21,len(c))
        records=[(t,x,y) for (x,y),t in sorted(c.items(),key=lambda p:(p[0][1],p[0][0]))]
        data=bytes(head)+b''.join(struct.pack('<Ihh',*r) for r in records)
        assert all(data[i]==src[i] for i in range(32) if i not in {*range(16,20),*range(21,25)})
        assert len(data)==32+8*len(c)
        decoded=[struct.unpack_from('<Ihh',data,32+8*i) for i in range(len(c))]
        assert decoded==records
        post=validate({(x,y):t for t,x,y in decoded},s)
        dests=[ROOT/f'{NAME}.LMF',SOURCE.parent/f'{NAME}.LMF']
        for dest in dests:
            if dest.exists() and dest.read_bytes()!=data:raise FileExistsError(dest)
        for dest in dests:dest.write_bytes(data);assert dest.read_bytes()==data
        assert SOURCE.read_bytes()==src
        report['export']={'paths':[str(p) for p in dests],'sha256':hashlib.sha256(data).hexdigest(),
                          'binary_roundtrip':True,'post_export_checks':post}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    guide=['# 압축05 — 필요한 것만', '',
           '아래부터 1·2, 한 층 위 3·4, 다음 5·6, 맨 위 얼음 7. 이동은 양끝 사다리.', '',
           '## 자석 1~6', '',
           '오른쪽을 보고, 발밑의 밝은 표시 3칸에서 가까운 쪽부터 한 칸씩 이동한다.',
           '각 표시에서 약 2초 앉았다가 일반 점프 한 번. 구르기·C 없이 같은 방법으로.',
           '2초는 비교를 위한 공통 조건일 뿐, 힘이 다 쌓이는 시간이라고 가정하지 않는다.',
           '가로 37은 자석 바로 옆→한 칸 더→두 칸 더. 세로 34·35는 바로 아래→옆 한 칸→옆 두 칸.',
           '왼쪽은 1개, 오른쪽은 첫 자석과 표시 위치를 그대로 대응시키고 그 왼쪽에 자석 1개를 추가했다.',
           '힘에 밀려 표시를 벗어나도 영상 좌표로 확인하니, 무리하게 버틸 필요 없다.', '',
           '## 얼음 7', '',
           '사다리로 올라가 중간/끝에서 점프+뒷굴. 내려온 평지에서 일반 점프 한 번 더.', '',
           '영상 하나에 좌표·키보드가 보이게. 천장이나 맵 끝에 닿으면 그 시도는 최대치로 쓰지 않는다.',
           '자석들 사이 간섭은 아직 미검증이다. 결과는 이 배치의 관측값이며 거리별 보편 법칙으로 바로 환산하지 않는다.',
           '원본맵과 종합04는 그대로 유지했다. 파일·배치 검사는 수행했으나 실제 게임 테스트는 아직이다.', '']
    (OUT/'안내.md').write_text('\n'.join(guide),encoding='utf-8')
    print(json.dumps({'dimensions':[W,H],'records':len(c),'magnets':{str(t):checks['tile_counts_decimal'][t] for t in (52,53,55)},
                      'min_other_fixture_distance':min(v['nearest_other_fixture_from_floor_reference'] for v in checks['cross_fixture_distances_cells']),
                      'preview':str(OUT/f'{NAME}_미리보기.png'),'export':report.get('export',{}).get('paths')},ensure_ascii=True))


if __name__=='__main__':main()
