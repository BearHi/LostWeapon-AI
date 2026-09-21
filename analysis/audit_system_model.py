"""Repeatable model audit against pinned, user-cleared files. No LMF writes.

Unknown tile behavior is explicitly unknown, never implicitly decorative.
The legacy diagnostic is measured against ground truth, not used to overrule it.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path

from cliff_validator import validate
from inspect_engine_evidence import lmf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis'/'system_model'
REFERENCES = [
    (Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF'),
     'cf7cae1336ccf53047d28da151c4979cebd40be7533c8e9871cba768f5fe06aa'),
    (ROOT/'암벽_신설안_v8_암반윤곽형.LMF',
     '242eec0f2cae677322563f34ba7b89295b8211da3534a83f24d9f5364df7e4fc'),
]

# Identity evidence comes from extracted editor sprites and the user's reports.
# Exact collision/force/timing laws are separate and remain unmeasured here.
IDENTITIES = {
    3: ('사다리', 'ladder', '사용자 설명: 방향키로 오르내림'),
    4: ('스프링', 'spring', '사용자 설명: 접촉 즉시 튐; 위가 막히면 무시'),
    7: ('밝은 사각 암반', 'square_solid', '사용자 확인 및 에디터 스프라이트'),
    8: ('갈색 사각 암반', 'square_solid', '사용자 확인 및 에디터 스프라이트'),
    16: ('상자 그림', 'unknown', '스프라이트 식별만; 에디터 16번 삼각형과 다름'),
    19: ('사각 얼음', 'ice_square', '에디터 13; 경사 얼음과 분리'),
    22: ('벽돌 경사', 'slope', '에디터 16; 보행 경사라는 사용자 설명'),
    27: ('오른쪽으로 올라가는 삼각 얼음', 'ice_slope', '에디터 1B; 이미지와 영상 대조'),
    32: ('오른쪽으로 내려가는 벽돌 경사', 'slope', '에디터 20; 이미지 식별'),
    37: ('오른쪽으로 내려가는 삼각 얼음', 'ice_slope', '에디터 25; 이미지와 영상 대조'),
    39: ('빈 스프라이트', 'unknown', '에디터 27; 그림이 없다는 사실은 무효과의 증거가 아님'),
    49: ('용암', 'instant_reset', '사용자 설명: 시작점 복귀; 구르기 통과 조건 미측정'),
    51: ('선풍기', 'fan', '사용자 설명: 낙하산을 펼쳐야 상승; 자석과 상호작용'),
    52: ('자석 34', 'magnet', '에디터 34; 거리별 힘 미측정'),
    53: ('자석 35', 'magnet', '에디터 35; 거리별 힘 미측정'),
    54: ('자석 36', 'magnet', '에디터 36; 거리별 힘 미측정'),
    55: ('자석 37', 'magnet', '에디터 37; 이번 측정맵에 사용'),
    82: ('물 모양 장식', 'decoration', '종합04의 실제 배치를 본 사용자 정정: 수영블록 아님; 진짜 수영 타일 ID는 미확인'),
    86: ('가시', 'damage', '사용자 설명: 무적시간 무시'),
    100: ('리스폰 표시 1', 'respawn', '사용자 설명 및 기준맵'),
    118: ('용암발사', 'projectile_hazard', '기존 타일 식별; 발사/충돌 시간 미측정'),
    119: ('들락가시', 'periodic_hazard', '사용자 설명: 같은 주기; 위상/피격 경계 미측정'),
    122: ('대전용 기지', 'competitive_base', '종합04의 실제 배치를 본 사용자 정정: 칼전 기지, 사라지는 블록 아님; 유즈맵 기능과 충돌은 미측정'),
}

SYSTEMS = [
    {'system': '기본 이동·점프·공중 구르기',
     'known': '일반 점프 약 5.8칸 관측, 점프+뒷굴 약 8칸 초과 사용자 확인',
     'missing': '좌우 입력별 속도, 구르기 발동 시점, 수평/수직 속도 갱신 순서',
     'priority': 1},
    {'system': '캐릭터·벽·모서리 충돌',
     'known': '사용자 설명: 9칸 기둥은 불가, 밑이 빈 한 줄 발판은 아래에서 올라설 수 있으나 넘어가지는 못함',
     'missing': '얇은 발판 진입/올라섬/넘어감의 별도 판정, 자세별 크기, 모서리 보정, 프레임 처리 순서',
     'priority': 1},
    {'system': '경사 보행·삼각 얼음',
     'known': '얼음 이후 점프 높이가 시도별로 다름; 평지에서도 높게 뛴 사례',
     'missing': '얼음 미끄럼 상태에서 좁은 틈 진입 판정; 일반 경사만으로 대체 불가; 힘의 저장·초기화 조건',
     'priority': 2},
    {'system': '방향별 자석',
     'known': '사용자 설명: 위치/거리/자세/입력에 따라 효과 달라짐; 종합04의 가로 자석 5·6번 배치는 영향이 닿지 않음',
     'missing': '힘의 범위와 수식, 자세별 누적 상태, 영향권 이탈 뒤 지속 여부',
     'priority': 2},
    {'system': '낙하산·선풍기',
     'known': '사용자 설명: 종합04 선풍기에서 구르기 없이 왼쪽 발판에 아슬하게 도달 가능',
     'missing': '개방 지연, 종단 하강속도, 조향, 선풍기 유효 범위와 힘',
     'priority': 3},
    {'system': '스프링·사다리·수영',
     'known': '사용자 설명: 종합04 왼쪽 스프링은 못 밟고 오른쪽은 밟힘; LMF82는 장식이므로 수영 실험 무효',
     'missing': '진입/이탈 조건, 속도 갱신, 입력 우선순위',
     'priority': 4},
    {'system': '가시·지뢰·용암·사라지는 블록',
     'known': '피해/즉시 복귀/주기성의 사용자 설명; LMF122는 기지로 정정, 사라지는 블록 ID 미확인',
     'missing': '정확한 충돌 범위, 타이머, 자세별 접촉, 체력과 재도전 경로',
     'priority': 4},
]


def reachable(report):
    adjacency = {s['index']: [] for s in report['surfaces']}
    for edge in report['edges']:
        adjacency[edge['from']].append(edge['to'])
    q = deque(report['graph']['start_candidates'])
    seen = set(q)
    while q:
        for dest in adjacency[q.popleft()]:
            if dest not in seen:
                seen.add(dest)
                q.append(dest)
    return seen


def tile_registry():
    bitmaps = json.loads((ROOT/'analysis'/'tilemap.json').read_text(encoding='utf-8'))
    result = {}
    for raw_id, bitmap in bitmaps.items():
        tile = int(raw_id)
        name, family, evidence = IDENTITIES.get(tile, ('미확인', 'unknown', '이미지 번호만 추출됨'))
        result[raw_id] = {'lmf_decimal': tile, 'editor_hex': f'{tile:02X}',
                          'bitmap_resource_id': bitmap, 'name': name,
                          'family': family, 'identity_evidence': evidence,
                          'engine_behavior_calibrated': False,
                          'unknown_is_passable': False}
    return result


def main():
    OUT.mkdir(exist_ok=True)
    registry = tile_registry()
    (OUT/'tile_registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8')
    audits = []
    for index, (path, expected_hash) in enumerate(REFERENCES):
        meta = lmf(path, 'pending_identity_check')
        unchanged = meta['sha256'] == expected_hash
        meta['clear_status'] = 'user_confirmed_clear' if unchanged else 'changed_file_clear_unverified'
        report = validate(path)
        seen = reachable(report)
        goals = set(report['graph']['goal_candidates'])
        start_surfaces = [s for s in report['surfaces'] if s['index'] in report['graph']['start_candidates']]
        start_checks = []
        for start in start_surfaces:
            above = [s for s in report['surfaces'] if s['y'] < start['y']]
            nearest_y = max((s['y'] for s in above), default=None)
            start_checks.append({'surface': start, 'nearest_higher_surface_y': nearest_y,
                                 'minimum_rise_cells': start['y']-nearest_y if nearest_y is not None else None,
                                 'surfaces_inside_vertical_cap': sum(start['y']-s['y'] <= report['parameters']['jump_backroll_max_up'] for s in above),
                                 'initial_spawn_pose_and_velocity_modeled': False})
        meta.update({'expected_sha256': expected_hash, 'matches_cleared_bytes': unchanged,
                     'legacy_path_count': len(report['graph']['paths']),
                     'legacy_reachable_surfaces': len(seen),
                     'legacy_graph_reaches_goal': bool(seen & goals),
                     'legacy_false_negative_against_user_clear': unchanged and not bool(seen & goals),
                     'legacy_pass_is_not_engine_proof': True,
                     'start_diagnostics': start_checks})
        audits.append(meta)
        (OUT/f'live_reference_{index}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # The purported 8.25-cell fixed-apex arc actually rises over 9 cells.
    peak, rise = 8.25, 8.
    extra = peak-rise/2
    actual_peak = (rise+4*extra)**2/(16*extra)
    example_params = json.loads((ROOT/'analysis'/'physics_params.example.json').read_text(encoding='utf-8'))
    audit = {'references': audits, 'legacy_arc_counterexample': {
        'configured_peak_cells': peak, 'target_rise_cells': rise,
        'actual_peak_cells': actual_peak, 'excess_cells': actual_peak-peak},
        'stale_example_jump_backroll_max_up': example_params['jump_backroll_max_up'],
        'gimmick_systems': SYSTEMS,
        'required_future_state': ['x', 'y', 'vx', 'vy', 'facing', 'pose', 'contact_surface',
                                  'air_roll_available', 'parachute_state', 'force_history_state_unknown',
                                  'health', 'hazard_timers', 'respawn_position'],
        'legacy_validator_sha256': hashlib.sha256((ROOT/'analysis'/'cliff_validator.py').read_bytes()).hexdigest(),
        'collision_kernel_status': 'synthetic_rectangle_geometry_only',
        'engine_model_ready_for_marginal_landings': False,
        'map_certification_policy': 'unsupported_or_uncalibrated_mechanics_remain_unverified'}
    (OUT/'system_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# 시스템 검증 현황', '',
             '원본 LMF와 클라이언트는 수정하거나 실행하지 않았다. 새 맵도 생성하지 않았다.', '',
             '## 실제 클리어와 검사기 결과를 분리', '',
             '| 기준맵 | 클리어 확인 파일과 동일 | 기존 검사기 경로 수 | 해석 |',
             '|---|---|---:|---|']
    for item in audits:
        meaning = '검사기가 실제 성공을 설명하지 못함' if item['legacy_false_negative_against_user_clear'] else '기존 그래프에서도 경로를 찾음; 물리 증명은 아님'
        if not item['matches_cleared_bytes']: meaning = '파일 변경됨; 과거 클리어 판정 승계 금지'
        lines.append(f"| {Path(item['path']).name} | {item['matches_cleared_bytes']} | {item['legacy_path_count']} | {meaning} |")
    lines += ['', '암벽수정1은 시작 바닥을 포함한 160개 표면 중 시작 표면 하나만 도달 가능하다고 나온다.',
              '그래프를 제한 없이 탐색해도 같으므로 단순히 경로 길이 제한 때문에 실패한 것은 아니다.',
              '출발 상세: 리스폰 표시 (15,237), 시작으로 선택한 바닥 Y=239, 가장 낮은 위쪽 착지면 Y=230.',
              '바닥에서의 높이차 9칸이 8.25칸 제한을 넘어서, 출발 연결 후보가 충돌 검사 전부터 0개다.',
              '즉 이 출발 실패를 포물선/벽 충돌 오류만으로 설명하면 틀린다.',
              '실제 리스폰 직후 캐릭터 위치·자세·속도와 좌표 기준점은 아직 영상과 대응되지 않았다.',
              '리스폰 타일 좌표와 몸의 바닥 좌표가 같다고 가정하거나, 바닥에서 재점프해야 한다고 가정하지 않는다.',
              '9칸이 보인다는 이유로 모든 점프 한계를 9칸 이상으로 늘리지도 않는다.',
              '추가 사용자 설명: 9칸 기둥과 밑이 빈 한 줄 발판은 다르며, 후자는 아래에서 올라설 수 있다.',
              '기준맵 끝 (17,230) 아래 Y=231~238이 빈 구조임을 별도 확인했다. 자세한 근거는 system_lab04/사용자정정.md.',
              '따라서 리스폰 상태뿐 아니라 얇은 발판 진입 판정 누락도 조사한다. 실제 동작 재현은 미완료다.',
              '이 결과로 맵을 수정하지 않는다. 실제 클리어를 설명하도록 모델을 보정해야 한다.', '',
              '## 기존 검사기에서 확인한 결함', '',
              f'1. 최대 8.25칸 설정, 목표 높이차 8칸인데 궤적 실제 최고점은 {actual_peak:.6f}칸이다.',
              '2. 이륙 첫 8%, 착지 마지막 8% 구간의 충돌 검사를 생략한다.',
              '3. 몸 크기 0.8×1.8칸, 가로 이동 한계는 아직 측정으로 확정하지 않았다.',
              '4. 삼각형 번호 16은 10진/16진 혼동이 남아 있고, 그 삼각형을 사각형으로 취급한다.',
              f"5. 예전 physics_params.example.json에는 뒷굴 상승 {example_params['jump_backroll_max_up']}칸이 남아 있다. 새 작업에 사용하지 않는다.",
              '6. 목표점에 맞춘 한 포물선은 점프→구르기→낙하산의 실제 입력 시퀀스가 아니다.',
              '기존 알고리즘은 과거 결과 비교용으로 보존하고 출력에 미보정 경고와 인증 불가 표시를 추가했다.', '',
              '## 새로 구현한 충돌 계산', '',
              '`analysis/collision_kernel.py`: 주어진 사각 몸과 직선 이동 구간을 연속 검사한다.',
              '검사 지점 사이의 얇은 벽과 출발·착지 직전 충돌도 검사하며, 바닥 접촉과 관통을 구분한다.',
              '19개 합성 수학 테스트: 바닥 보행/점프/착지, 1칸 착지, 1칸·2칸 통로, 천장, 얇은 벽,',
              '진입·이탈, 코너 접촉, 1/1024칸 관통, 잘못된 입력 등을 검사했다.',
              '**수학적 사각형 충돌만 검증했다. 게임이 1/1024칸 정밀도로 재현된다는 뜻은 아니다.**',
              '영상 점들을 직선으로 이은 경로는 실제 곡선과 다를 수 있으며, 자세별 히트박스도 미측정이다.',
              '경사·자석·팬·타이머·충돌 반응과 전체 경로 탐색은 이 모듈에 구현되지 않았다.', '',
              '## 암벽 외 기믹까지 다루기 위한 상태와 순서', '',
              '| 단계 | 시스템 | 남은 핵심 |', '|---|---|---|']
    lines += [f"| {s['priority']} | {s['system']} | {s['missing']} |" for s in SYSTEMS]
    lines += ['', '같은 좌표라도 속도·자세·직전 얼음/자석 영향·공중 구르기 사용 여부·낙하산 상태가 다르면 다른 상태다.',
              '이는 필요한 모델 구조이며, 현재 게임 내부 저장 변수를 확인했다는 의미는 아니다.', '',
              '## 타일 번호와 실행 파일 근거', '',
              'tile_registry.json에 전체 143개 ID의 LMF 10진수, 에디터 16진수, 비트맵 리소스를 저장했다.',
              '효과 미확인 타일은 빈 공간이나 장식으로 처리하지 않는다. 37(10진)은 얼음 경사이며 자석 37(16진)은 55다.',
              '클라이언트 실행 파일 두 개의 해시는 동일하며, COFF 함수 심볼은 0개였다.',
              '점프/스프링/바람 효과음 문자열만으로 물리식을 알아낼 수는 없다. 물리 함수 자체는 아직 식별하지 못했다.',
              '편집기에는 함수 심볼이 있지만 편집 기능을 게임 물리로 간주하지 않는다.', '',
              '## 바로 다음에 필요한 일', '',
              '추가 대량 테스트맵보다, 기준맵 출발부에서 실제 가능한 이륙 위치와 몸/모서리 판정을 먼저 맞춘다.',
              '기존 영상과 이 LMF가 정확히 대응하는지 확인한 뒤 성공 점프를 접촉 전후 프레임 단위로 연결한다.',
              '그다음 얼음/자석에서 받은 상태가 착지·대기·다음 점프 중 언제 바뀌는지 분리한다.',
              '자료가 부족한 항목만 모아 작은 테스트맵 하나와 짧은 동작 조건으로 요청한다.', '']
    (OUT/'시스템검증_현황.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'references': [{k:r[k] for k in ('path','matches_cleared_bytes','legacy_reachable_surfaces','legacy_false_negative_against_user_clear')} for r in audits],
                      'arc_counterexample':audit['legacy_arc_counterexample'],
                      'registry_entries':len(registry)},ensure_ascii=True,indent=2))


if __name__ == '__main__':
    main()
