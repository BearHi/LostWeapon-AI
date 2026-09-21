"""One compact 12-station observation LMF. Preview before explicit export.

This is a measurement fixture, not a physics-certified challenge map.
All source maps are read-only. No overlapping records, no invented tile IDs.
Historical layout retained: user_feedback.json supersedes its original test
instructions and tile identities (82 decoration; 122 competitive base).
"""
import argparse
import hashlib
import json
import struct
import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'analysis'/'video_runtime'))
from PIL import Image, ImageDraw, ImageFont

OUT = ROOT/'analysis'/'system_lab04'
NAME = '물리측정_종합04'
SOURCE = Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF')
W, H = 200, 160
FLOORS = [150,112,74,36]
SHAFTS = [4,68,132,196]
DIGITS = ['111101101101111','010110010010111','111001111100111',
          '111001111001111','101101111001001','111100111001111',
          '111100111101111','111001010010010','111101111101111',
          '111101111001111']
TITLES = ['기본 점프 · 5 / 8 / 9칸','모서리 · 2칸 / 1칸 틈','낙하산 · 수평 이동',
          '얼음 경사 · 힘의 유지','가로 자석 36','가로 자석 37',
          '세로 자석 34','세로 자석 35','선풍기 + 낙하산',
          '스프링','물 + 사다리','가시 · 사라짐 · 용암']
INSTRUCTIONS = [
    '바닥에서 5칸은 점프, 8·9칸은 점프+뒷굴로 각각 시도. 발판끼리 이어 뛰지 않기.',
    '왼쪽 2칸 틈을 지나고, 오른쪽 경사 끝 1칸 틈은 네가 아는 자세로 비벼보기. 안 되면 패스.',
    '사다리로 왼쪽 위에 올라가 오른쪽으로 점프+뒷굴+C. 가까운 곳이나 먼 곳에 착지.',
    '사다리로 올라가 얼음 중간/끝에서 각각 점프+뒷굴. 내려와 평지에서 한 번 더 점프.',
    '자석 바로 아래와 옆에서, 바로 점프 / 잠깐 앉았다 점프를 비교. 시간은 편하게.',
    '5번처럼 해보고, 가능하면 보는 방향만 바꿔 한 번 더.',
    '자석 아래에서 점프+뒷굴. 바로 아래와 옆으로 조금 벗어난 곳을 비교.',
    '7번처럼 자석 바로 아래와 옆에서 점프+뒷굴을 비교.',
    '선풍기 바로 위 공중에서 C를 펴 올라간 뒤, 옆 발판으로 빠져나오기.',
    '왼쪽 낮은 천장 아래 스프링과 오른쪽 열린 스프링을 밟아보기.',
    '물에 들어갔다가 방향키로 나와보기. 옆 사다리에서 점프/구르기도 해보기.',
    '가시/들락가시를 네 방식으로 지나고, 사라지는 블록을 밟았다 다시 타보기. 용암 구르기는 마지막.',
]


def layout():
    cells = {}
    stations = []
    def put(x,y,t=8):
        if not (0<=x<W and 0<=y<H): raise ValueError((x,y))
        cells[x,y] = t
    def box(x1,y1,x2,y2,t=8):
        for y in range(y1,y2+1):
            for x in range(x1,x2+1): put(x,y,t)
    def remove(x1,y1,x2,y2):
        for y in range(y1,y2+1):
            for x in range(x1,x2+1): cells.pop((x,y),None)
    box(0,0,0,H-1);box(W-1,0,W-1,H-1);box(0,H-2,W-1,H-1)
    # Each experiment has its own floor. Below it is a four-cell clear
    # bypass corridor, with continuous vertical ladders between columns.
    for floor in FLOORS:
        box(1,floor+6,W-2,floor+6)
        for col in range(3):
            x0=col*64
            box(x0+8,floor,x0+63,floor+1)
    for x in SHAFTS:
        remove(x-2,5,x+2,H-3)
        box(x,5,x,H-3,3)
    # Restore bottom walkway around shaft ends; all shaft landings supported.
    box(1,H-2,W-2,H-2)
    for i,title in enumerate(TITLES):
        col,row=i%3,i//3
        x0=col*64; f=FLOORS[row]
        st={'number':i+1,'title':title,'column':col,'floor_y':f,
            'bounds':[x0+8,f-30,x0+63,f+1], 'instruction':INSTRUCTIONS[i],
            'entry':[x0+10,f-2], 'features':[]}
        stations.append(st)
        # Actual in-game section number, high and left of the test apparatus.
        for j,digit in enumerate(str(i+1)):
            for k,bit in enumerate(DIGITS[int(digit)]):
                if bit=='1':put(x0+10+j*4+k%3,f-28+k//3,7)
        if i==0:
            put(x0+12,f-2,100)
            for x,rise in [(x0+26,5),(x0+40,8),(x0+53,9)]:
                box(x,f-rise,x+1,f-1)
                st['features'].append({'kind':'landing','x':x,'y':f-rise,'rise':rise,'width':2})
        elif i==1:
            box(x0+20,f-3,x0+29,f-3) # Two empty cells underneath.
            # A normal brick slope feeds an optional one-cell-high pocket.
            for j in range(4):
                put(x0+40+j,f-1-j,22)
                box(x0+40+j,f-j,x0+40+j,f-1)
            box(x0+44,f-4,x0+49,f-1)
            box(x0+44,f-6,x0+49,f-6) # y=f-5 is the sole empty cell.
            st['features']=[{'kind':'clearance_probe','x':[x0+20,x0+29],'empty_height':2},
                            {'kind':'optional_clearance_probe','x':[x0+44,x0+49],'empty_height':1}]
        elif i==2:
            box(x0+16,f-10,x0+21,f-1)
            box(x0+14,f-11,x0+14,f-1,3)
            box(x0+36,f-6,x0+38,f-6)
            box(x0+50,f-6,x0+53,f-6)
            st['features']=[{'kind':'launch','x':x0+21,'y':f-10},
                            {'kind':'landing','x':x0+36,'y':f-6,'horizontal_edge_gap':14},
                            {'kind':'landing','x':x0+50,'y':f-6,'horizontal_edge_gap':28}]
        elif i==3:
            box(x0+17,f-8,x0+21,f-1)
            box(x0+15,f-9,x0+15,f-1,3)
            for j in range(8):
                put(x0+22+j,f-8+j,37)
                box(x0+22+j,f-7+j,x0+22+j,f-1)
            # Rock runway after slope: intentionally NOT square ice.
            for x in (x0+31,x0+40,x0+51):put(x,f,7)
            st['features']=[{'kind':'ice_descent','length':8,'start':[x0+22,f-8]},
                            {'kind':'post_ice_rock_runway','x':[x0+30,x0+62]}]
        elif i in (4,5,6,7):
            tile={4:54,5:55,6:52,7:53}[i]
            pos=(x0+36,f-(6 if i in (4,5) else 8))
            put(*pos,tile)
            for x in (x0+30,x0+36,x0+42):put(x,f,7)
            st['features']=[{'kind':'magnet','id_decimal':tile,'editor_hex':f'{tile:02X}',
                            'xy':list(pos),'empty_cells_below':f-pos[1]-1,
                            'force_range_verified':False}]
        elif i==8:
            put(x0+32,f-1,51)
            box(x0+20,f-10,x0+23,f-10)
            box(x0+43,f-15,x0+47,f-15)
            st['features']=[{'kind':'fan','xy':[x0+32,f-1],'clear_column_to_y':f-29},
                            {'kind':'side_landing','xy':[x0+43,f-15]}]
        elif i==9:
            put(x0+23,f,4);put(x0+46,f,4)
            box(x0+20,f-3,x0+26,f-3)
            st['features']=[{'kind':'spring_low_ceiling','xy':[x0+23,f]},
                            {'kind':'spring_open','xy':[x0+46,f],'map_top_may_clip':True}]
        elif i==10:
            box(x0+23,f-4,x0+24,f-1)
            box(x0+25,f-5,x0+36,f-1,82)
            box(x0+37,f-4,x0+38,f-1)
            box(x0+40,f-10,x0+40,f-1,3)
            box(x0+42,f-9,x0+46,f-9)
            st['features']=[{'kind':'water','id_decimal':82,'editor_hex':'52',
                            'bounds':[x0+25,f-5,x0+36,f-1]},
                            {'kind':'ladder','x':x0+40,'top_y':f-10}]
        elif i==11:
            put(x0+20,f-1,86);put(x0+29,f-1,119)
            for x in range(x0+36,x0+40):put(x,f-4,122)
            for x in range(x0+49,x0+52):put(x,f-1,49)
            st['features']=[{'kind':'spike','xy':[x0+20,f-1]},
                            {'kind':'moving_spike','xy':[x0+29,f-1]},
                            {'kind':'disappearing','bounds':[x0+36,f-4,x0+39,f-4]},
                            {'kind':'lava_optional_last','bounds':[x0+49,f-1,x0+51,f-1]}]
    return cells,stations


def checks(cells,stations):
    counts=Counter(cells.values())
    assert counts[100]==1 and counts[52]==counts[53]==counts[54]==counts[55]==1
    assert all(0<=x<W and 0<=y<H for x,y in cells)
    assert counts[37]==8 and counts[51]==1 and counts[4]==2
    assert all(cells[x,y]==3 for x in SHAFTS for y in range(5,H-2))
    assert all(cells.get((x,y)) in (None,3) for f in FLOORS
               for y in range(f+2,f+6) for x in range(1,W-1))
    # Exact static connectivity of 1x2-cell upright pockets via cardinal moves.
    # Vertical free-space steps are only a topology test, not locomotion proof.
    solids={7,8,22,37} # Triangles treated as whole squares ONLY for this bypass check.
    passable=lambda x,y: 0<x<W-1 and 1<=y<H-1 and all(cells.get((x,yy)) not in solids for yy in (y-1,y))
    spawn=next(p for p,t in cells.items() if t==100)
    visited={spawn}; queue=deque([spawn])
    while queue:
        x,y=queue.popleft()
        for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if p not in visited and passable(*p):visited.add(p);queue.append(p)
    assert all(tuple(s['entry']) in visited for s in stations)
    for s in stations:
        for feature in s['features']:
            if feature['kind']=='magnet':
                x,y=feature['xy']
                assert all((x,yy) not in cells for yy in range(y+1,s['floor_y']))
            if feature['kind']=='fan':
                x,y=feature['xy']
                assert all((x,yy) not in cells for yy in range(feature['clear_column_to_y'],y))
    return {'bounds':True,'unique_spawn':True,'overlapping_records':False,
            'four_cell_bypass_corridors_clear':True,'four_continuous_access_ladders':True,
            'all_12_entries_connected_in_static_1_by_2_pocket_test':True,
            'topology_test_is_not_movement_simulation':True,
            'magnet_burial_check':True,'fan_vertical_column_clear':True,
            'game_tested':False,'magnetic_isolation_verified':False,
            'engine_clear_certified':False,'tile_counts_decimal':dict(counts)}


def font(size):return ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',size)


def render(cells,stations):
    colors={8:'#8b694a',7:'#edd99e',3:'#ca99ed',100:'#66f4a2',22:'#cba181',
            37:'#72d9ee',52:'#ffbe63',53:'#ffbe63',54:'#ffbe63',55:'#ffbe63',
            51:'#829ffa',4:'#f2da6a',82:'#5c96e5',86:'#ff626a',119:'#ff626a',
            122:'#d5e3ee',49:'#ff713f'}
    mini=Image.new('RGB',(W,H),'#152330')
    for p,t in cells.items():mini.putpixel(p,tuple(bytes.fromhex(colors[t][1:])))
    mini.resize((W*6,H*6),Image.Resampling.NEAREST).save(OUT/f'{NAME}_전체도트.png')
    image=Image.new('RGB',(1240,1100),'#152330');d=ImageDraw.Draw(image)
    d.text((20,12),'종합04 · 12구역 / 200 × 160칸',font=font(26),fill='#f3f6fa')
    d.text((20,52),'아래 1 → 3, 한 층 위 4 → 6 순서. 막히면 보라색 사다리와 각 층 밑 통로로 이동.',font=font(18),fill='#d1dfe8')
    image.paste(mini.resize((1200,960),Image.Resampling.NEAREST),(20,96))
    for s in stations:
        x0=s['column']*64; yy=96+(s['floor_y']-28)*6
        # Label only empty sky, never paint over an actual corridor/deck.
        d.text((20+(x0+20)*6,yy),s['title'],font=font(15),fill='#f3f6fa')
    d.text((20,1069),'시험 목표는 미검증 · 성공/실패 모두 측정 자료 · 막히는 목표는 건너뛰기 가능',font=font(17),fill='#d1dfe8')
    image.save(OUT/f'{NAME}_미리보기.png')
    mapping=json.loads((ROOT/'analysis'/'tilemap.json').read_text(encoding='utf-8'))
    assets={}
    for t in set(cells.values()):
        tile=Image.open(ROOT/'analysis'/f'bitmap_{mapping[str(t)]}.bmp').convert('RGB').resize((12,12),Image.Resampling.NEAREST)
        mask=Image.new('L',tile.size)
        mask.putdata([0 if r>220 and g<50 and b>220 else 255 for r,g,b in tile.getdata()])
        assets[t]=(tile,mask)
    # Individual views preserve all headroom and actual triangle orientation.
    for s in stations:
        x1,y1,x2,y2=s['bounds'];x1-=3;x2+=3
        pic=Image.new('RGB',((x2-x1+1)*12,470),'#152330');pd=ImageDraw.Draw(pic)
        pd.text((10,8),f"{s['number']:02}  {s['title']}",font=font(22),fill='#f3f6fa')
        for (x,y),t in cells.items():
            if x1<=x<=x2 and y1<=y<=y2:
                tile,mask=assets[t];pic.paste(tile,((x-x1)*12,44+(y-y1)*12),mask)
        # Wrap the simple instruction, keeping it readable in the exported crop.
        text=s['instruction'];lines=[];line=''
        for c in text:
            if pd.textlength(line+c,font=font(15))>pic.width-20:lines.append(line);line=''
            line+=c
        lines.append(line)
        for j,line in enumerate(lines):pd.text((10,436+j*18),line,font=font(15),fill='#d1dfe8')
        pic.save(OUT/f"구역_{s['number']:02}.png")


def export(cells,preview_digest):
    marker=json.loads((OUT/'preview_manifest.json').read_text(encoding='utf-8'))
    if marker['layout_sha256']!=preview_digest:raise ValueError('Layout changed since preview')
    original=SOURCE.read_bytes()[:32];header=bytearray(original)
    records=[(t,x,y) for (x,y),t in sorted(cells.items(),key=lambda p:(p[0][1],p[0][0]))]
    struct.pack_into('<HH',header,16,W,H);struct.pack_into('<I',header,21,len(records))
    data=bytes(header)+b''.join(struct.pack('<Ihh',*r) for r in records)
    assert len(data)==32+8*len(records)
    reread=[struct.unpack_from('<Ihh',data,32+i*8) for i in range(len(records))]
    assert reread==records and {(x,y):t for t,x,y in reread}==cells
    assert all(data[i]==original[i] for i in range(32) if i not in {*range(16,20),*range(21,25)})
    destinations=[ROOT/f'{NAME}.LMF',SOURCE.parent/f'{NAME}.LMF']
    for dest in destinations:
        if dest.exists() and dest.read_bytes()!=data:raise FileExistsError(dest)
    for dest in destinations:
        dest.write_bytes(data)
        assert dest.read_bytes()==data
    # Re-validate the actually serialized, read-back map, not just the drawing.
    _,stations=layout();post=checks({(x,y):t for t,x,y in reread},stations)
    return {'paths':[str(p) for p in destinations],'sha256':hashlib.sha256(data).hexdigest(),
            'records':len(records),'binary_roundtrip':True,'post_export_checks':post}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--export',action='store_true');args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    cells,stations=layout();check=checks(cells,stations)
    digest=hashlib.sha256(json.dumps(sorted((x,y,t) for (x,y),t in cells.items())).encode()).hexdigest()
    source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    report={'name':NAME,'dimensions':[W,H],'stations':stations,'checks':check,'layout_sha256':digest,
            'source_lmf_sha256':source_hash,
            'limits':['Magnet fields may cross stations; walls do not establish isolation.',
                      'Ceiling/map-edge clipped flights are not maximum-height/distance evidence.',
                      'Airborne state, ice force history and respawn dynamics are uncalibrated.',
                      'The 9-cell landing and 1-cell pocket are optional boundary probes, not promised clears.',
                      'Mines/hell doors omitted: their IDs are not confidently identified.'],
            'capture':'One continuous video with character-side coordinates and keyboard overlay; no fixed HUD coordinates.'}
    if args.export:report['export']=export(cells,digest)
    else:
        render(cells,stations)
        (OUT/'preview_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_hash
    feedback_path=OUT/'user_feedback.json'
    if feedback_path.exists():
        report['superseding_user_feedback']=json.loads(feedback_path.read_text(encoding='utf-8'))
        report['original_instructions_status']='superseded_see_user_feedback'
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    guide=['# 종합04 — 이렇게만 해줘', '',
           '아래층 1→2→3, 한 층 위 4→5→6, 그 위 7→8→9, 맨 위 10→11→12.',
           '구역은 큰 암반 숫자로 표시했다. 세로 사다리와 각 층 밑 통로로 어느 구역이든 건너뛸 수 있다.',
           '영상은 좌표·키보드 보이게 한 번에 찍으면 된다. 각 항목 1~2번, 미묘하면 몇 번 더.',
           '막히면 오래 붙잡지 말고 넘어가도 된다. 성공/실패 모두 필요하다.', '',
           '| 번호 | 할 일 |','|---|---|']
    guide += [f"| {s['number']} · {s['title']} | {s['instruction']} |" for s in stations]
    guide += ['', '주의: 낙하산 접기는 사용하지 않아도 된다. 가시·용암은 마지막 구역에만 있으며 용암은 시작점으로 돌려보낼 수 있다.',
              '자석 4개는 다른 구역에 하나씩 배치했다. 서로 영향이 없다는 것은 아직 검증되지 않았으므로 숫자는 이 배치의 관측값으로 기록한다.',
              '천장/맵 끝에 부딪히면 그 시도는 최대 거리·최대 높이 측정에서 제외한다.',
              '9칸과 1칸 틈은 일부러 성공 여부를 알아보는 선택 실험이다. 나머지 구역 접근에 필요하지 않다.',
              '지뢰·지옥문은 타일 ID를 확정하지 못해 이번에는 넣지 않았다.',
              '파일 구조·통로·사다리·매립 여부를 검사했으며, 실제 게임 클리어/물리 시뮬레이션 인증은 하지 않았다.', '']
    if feedback_path.exists():
        guide[2:2]=['> 사용자 정정이 최초 안내보다 우선한다. 2·5·6·11·12번 실험 취소.',
                    '> 1번 9칸 기둥과 3번 먼 발판은 불가로 기록, 9번 왼쪽은 구르기 없이 아슬하게 가능.',
                    '> 4·7·8번은 사용자가 나중에 하기로 했다. 82는 장식, 122는 대전용 기지다.',
                    '> 자세한 내용: 사용자정정.md. 아래는 최초 배치 기록이다.', '']
    (OUT/'짧은안내.md').write_text('\n'.join(guide),encoding='utf-8')
    print(json.dumps({'preview':str(OUT/f'{NAME}_미리보기.png'),'layout_sha256':digest,
                      'checks':check,'export':report.get('export')},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
