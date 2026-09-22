"""LostWeapon Procedural Physics Curriculum Autonomous Trainer.

Executes autonomous training on the 21 physical variation maps without touching legacy maps.
Zero token cost - runs 100% locally on x86 native emulator.
Records best routes to checkpoints/physics_curriculum_routes.json and appends to TRAINING_LOG.md.
"""
import sys
import os
import time
import json
from pathlib import Path

# Force UTF-8 console output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(r"c:\Users\sang\Desktop\로스트웨폰 맵")
sys.path.insert(0, str(ROOT / "native_harness"))

from api import NativeTrainingAPI
from lmf_injector import NativeLmfOracle
from snapshot_selector import snapshot_for_map
from native_env import LostWeaponEnv, ACTIONS

MAPS_DIR = ROOT / "훈련용맵" / "physics_curriculum"
LOG_FILE = ROOT / "TRAINING_LOG.md"
ROUTES_FILE = ROOT / "checkpoints" / "physics_curriculum_routes.json"
ROUTES_FILE.parent.mkdir(parents=True, exist_ok=True)


# Stage categories and specific controller strategies
CURRICULUM_STAGES = [
    # STAGE 1: 기본 점프 & 단차
    ("stg1_01_gap2.LMF", "jump", "1-1. 2칸 기본 갭 도약 (64px)"),
    ("stg1_02_gap3.LMF", "jump", "1-2. 3칸 갭 도약 (96px)"),
    ("stg1_03_gap4.LMF", "jump", "1-3. 4칸 롱점프 도약 (128px)"),
    ("stg1_04_gap5.LMF", "jump", "1-4. 5칸 점프 한계 도약 (160px)"),
    ("stg1_05_step3.LMF", "jump_step", "1-5. 3칸 단차 등반 (96px)"),
    ("stg1_06_step5.LMF", "jump_step", "1-6. 5칸 단차 한계 등반 (160px)"),

    # STAGE 2: 점프뒷굴 고벽 등반
    ("stg2_01_wall6.LMF", "backroll", "2-1. 6칸 고벽 점프뒷굴 (192px)"),
    ("stg2_02_wall7.LMF", "backroll", "2-2. 7칸 고벽 점프뒷굴 (224px)"),
    ("stg2_03_wall8.LMF", "backroll", "2-3. 8칸 한계 절벽 점프뒷굴 (256px)"),
    ("stg2_04_ceiling_wall6.LMF", "backroll_low", "2-4. 오버행 천장 6칸 고벽"),

    # STAGE 3: 1칸 기둥 안착 & 제자리칼 브레이크
    ("stg3_01_pillar1_knife.LMF", "pillar_knife", "3-1. 1칸 좁은 기둥 안착 (4번칼 브레이크)"),
    ("stg3_02_stepping_pillars.LMF", "stepping_stones", "3-2. 연속 1칸 징검다리 안착"),

    # STAGE 4: 사라지는 블록 12틱 윈도우
    ("stg4_01_disp_single.LMF", "disp_single", "4-1. 단일 붕괴 발판 도약 (12틱 탈출)"),
    ("stg4_02_disp_double.LMF", "disp_double", "4-2. 연속 붕괴 발판 주파"),

    # STAGE 5: 낙하산 장거리 활강
    ("stg5_01_glide18.LMF", "glide_long", "5-1. 18칸 심연 협곡 활강 (576px)"),
    ("stg5_02_glide22.LMF", "glide_huge", "5-2. 22칸 초장거리 활강 (704px)"),
    ("stg5_03_ceiling_drop.LMF", "ceiling_drop", "5-3. 저천장 모서리 드랍 활강"),

    # STAGE 6: 공중 칼질 연계
    ("stg6_01_knife_ledge.LMF", "knife_ledge", "6-1. 점프뒷굴칼 고벽 올라타기 (+119px)"),
    ("stg6_02_knife_parachute.LMF", "knife_glide", "6-2. 공중 칼질 후 낙하산 연계"),

    # STAGE 7: 스프링 초고공 도약
    ("stg7_01_spring11.LMF", "spring_high", "7-1. 11칸 고벽 스프링 도약 (352px)"),
    ("stg7_02_spring12_wide.LMF", "spring_wide", "7-2. 와이드 12칸 스프링 횡단"),
]


def solve_stage(api, strategy: str, goal_x: float, goal_y: float, ground_y: float):
    """Execute adaptive physics search adhering to LOSTWEAPON_PHYSICS_MASTER_RULES.md."""
    
    # Adaptive trial parameter generators
    if strategy in ("jump", "jump_step"):
        trial_params = [
            {"trigger_x": 180.0, "jump_dur": 22},
            {"trigger_x": 210.0, "jump_dur": 24},
            {"trigger_x": 236.0, "jump_dur": 26}, # Ledge edge jump!
            {"trigger_x": 246.0, "jump_dur": 28}, # Precision edge jump!
        ]
    elif strategy in ("backroll", "backroll_low"):
        trial_params = [
            {"trigger_x": 160.0, "apex": 28},
            {"trigger_x": 170.0, "apex": 28},
            {"trigger_x": 150.0, "apex": 27},
            {"trigger_x": 160.0, "apex": 29},
        ]
    elif strategy in ("pillar_knife", "stepping_stones"):
        trial_params = [
            {"trigger_x": 140.0, "knife_tick": 34},
            {"trigger_x": 150.0, "knife_tick": 33},
            {"trigger_x": 160.0, "knife_tick": 32},
            {"trigger_x": 130.0, "knife_tick": 35},
        ]
    elif strategy in ("disp_single", "disp_double"):
        trial_params = [
            {"jump_delay": 2},
            {"jump_delay": 5},
            {"jump_delay": 8},
            {"jump_delay": 10},
        ]
    elif strategy in ("glide_long", "glide_huge"):
        trial_params = [
            {"trigger_x": 150.0, "chute_air_t": 28, "max_t": 350},
            {"trigger_x": 160.0, "chute_air_t": 26, "max_t": 380},
            {"trigger_x": 140.0, "chute_air_t": 24, "max_t": 400},
        ]
    elif strategy == "ceiling_drop":
        trial_params = [{"drop_deploy": True}]
    elif strategy in ("knife_ledge", "knife_glide"):
        trial_params = [
            {"trigger_x": 150.0, "knife_delay": 29},
            {"trigger_x": 160.0, "knife_delay": 28},
            {"trigger_x": 140.0, "knife_delay": 30},
        ]
    elif strategy in ("spring_high", "spring_wide"):
        trial_params = [{"hold_right": True, "max_t": 350}]
    else:
        trial_params = [{}]

    best_final_st = None
    best_actions = []
    
    for attempt_idx, params in enumerate(trial_params, 1):
        api.reset()
        for _ in range(15): api.step(1, ())
        
        plan_actions = []
        success = False
        clear_tick = 0
        
        def step_act(act):
            nonlocal clear_tick, success
            plan_actions.append(act)
            st = api.step(1, act)
            t = len(plan_actions)
            if abs(st["x"] - goal_x) <= 36.0 and abs(st["y"] - goal_y) <= 48.0:
                success = True
                clear_tick = t
            return st

        # Strategy Execution
        if strategy in ("jump", "jump_step"):
            trig = params["trigger_x"]
            dur = params["jump_dur"]
            jump_t = None
            for t in range(250):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if st["x"] >= trig and jump_t is None:
                    jump_t = t
                    act = ("RIGHT", "UP")
                elif jump_t is not None and (t - jump_t) < dur:
                    act = ("RIGHT", "UP")
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy in ("backroll", "backroll_low"):
            trig = params["trigger_x"]
            apex = params["apex"]
            jump_t = None
            for t in range(250):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if jump_t is None and st["x"] >= trig:
                    jump_t = t
                    act = ("RIGHT", "UP")
                elif jump_t is not None:
                    air_t = t - jump_t
                    if air_t < apex: act = ("RIGHT", "UP")
                    elif air_t == apex: act = ("LEFT",)
                    elif air_t < apex + 10: act = ("RIGHT", "DOWN")
                    else: act = ("RIGHT",)
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy in ("pillar_knife", "stepping_stones"):
            api.step(1, ("4",)) # Greatsword
            trig = params["trigger_x"]
            ktick = params["knife_tick"]
            jump_t = None
            hop_t = None
            for t in range(260):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if jump_t is None and st["x"] >= trig:
                    jump_t = t
                    act = ("RIGHT", "UP")
                elif jump_t is not None and hop_t is None:
                    air_t = t - jump_t
                    if air_t < 28: act = ("RIGHT", "UP")
                    elif air_t == 28: act = ("LEFT",)
                    elif air_t < 32: act = ("RIGHT", "DOWN")
                    elif air_t == ktick: act = ("Z",) # Precision Knife brake!
                    elif air_t > 50 and st["y"] == ground_y:
                        hop_t = t
                        act = ("RIGHT", "UP")
                    else: act = ("RIGHT",)
                elif hop_t is not None:
                    act = ("RIGHT", "UP") if (t - hop_t) < 20 else ("RIGHT",)
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy in ("disp_single", "disp_double"):
            jdelay = params["jump_delay"]
            stepped_t = None
            jump_done = False
            for t in range(250):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                # Raw124 is at x=8 (256px) or x=9 (288px)
                if st["x"] >= 240.0 and stepped_t is None:
                    stepped_t = t
                if stepped_t is not None and not jump_done:
                    if (t - stepped_t) >= jdelay:
                        act = ("RIGHT", "UP")
                        jump_done = True
                    else:
                        act = ("RIGHT",)
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy in ("glide_long", "glide_huge"):
            trig = params["trigger_x"]
            cair = params["chute_air_t"]
            max_t = params.get("max_t", 300)
            jump_t = None
            for t in range(max_t):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if jump_t is None and st["x"] >= trig:
                    jump_t = t
                    act = ("RIGHT", "UP")
                elif jump_t is not None:
                    air_t = t - jump_t
                    if air_t < cair: act = ("RIGHT", "UP")
                    elif air_t >= cair: act = ("RIGHT", "C")
                    else: act = ("RIGHT",)
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy == "ceiling_drop":
            for t in range(250):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if st["y"] > 192.5: act = ("RIGHT", "C")
                else: act = ("RIGHT",)
                step_act(act)

        elif strategy in ("knife_ledge", "knife_glide"):
            api.step(1, ("1",))
            trig = params["trigger_x"]
            kdelay = params["knife_delay"]
            jump_t = None
            for t in range(260):
                st = api.read_state()
                if success or st["y"] > 470.0: break
                if jump_t is None and st["x"] >= trig:
                    jump_t = t
                    act = ("RIGHT", "UP")
                elif jump_t is not None:
                    air_t = t - jump_t
                    if air_t < 28: act = ("RIGHT", "UP")
                    elif air_t == 28: act = ("LEFT",)
                    elif air_t < 32: act = ("RIGHT", "DOWN")
                    elif air_t == kdelay: act = ("RIGHT", "Z") # Knife forward boost!
                    elif air_t > kdelay + 10 and strategy == "knife_glide":
                        act = ("RIGHT", "C")
                    else: act = ("RIGHT",)
                else:
                    act = ("RIGHT",)
                step_act(act)

        elif strategy in ("spring_high", "spring_wide"):
            max_t = params.get("max_t", 320)
            for t in range(max_t):
                st = api.read_state()
                if success or st["y"] > 520.0: break
                act = ("RIGHT",)
                step_act(act)

        best_final_st = api.read_state()
        best_actions = plan_actions
        if success:
            return True, clear_tick, best_final_st, best_actions

    return False, 0, best_final_st, best_actions


def main():
    print("=" * 82)
    print("  로스트웨폰 물리 법칙 마스터 커리큘럼 21종 변형 맵 자율 학습기 (ZERO-TOKEN)")
    print("=" * 82)
    print("• 기반 법전: LOSTWEAPON_PHYSICS_MASTER_RULES.md (단일 최고 규범)")
    print("• 대상 데이터: 물리 한계선(186px, 270px, 506px 등) 기반 21종 절차적 변형 맵 전수")
    print("• 레거시 맵(훈1~20): 완전 배제 (일반화 오염 차단)\n")

    saved_routes = {}
    if ROUTES_FILE.exists():
        try:
            saved_routes = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            saved_routes = {}

    passed_count = 0
    total_stages = len(CURRICULUM_STAGES)

    for idx, (map_filename, strategy, stage_title) in enumerate(CURRICULUM_STAGES, 1):
        map_path = MAPS_DIR / map_filename
        if not map_path.exists():
            print(f"[{idx:2d}/{total_stages}] {stage_title:<32} | [오류: LMF 파일 없음]")
            continue

        w, h, recs = NativeLmfOracle.parse_lmf(map_path)
        spawn = next(r for r in recs if r[0] == 100)
        goal = next(r for r in recs if r[0] == 140)
        
        goal_x = goal[1] * 32.0 + 16.0
        goal_y = goal[2] * 32.0
        ground_y = (spawn[2] + 1) * 32.0

        snap_path = snapshot_for_map(ROOT / "native_harness", map_path)
        api = NativeTrainingAPI(snap_path, map_path, track_dirty=True)

        start_time = time.monotonic()
        ok, clear_tick, final_st, actions = solve_stage(api, strategy, goal_x, goal_y, ground_y)
        elapsed = time.monotonic() - start_time

        status_str = "🚩 CLEAR" if ok else "❌ FAIL"
        if ok:
            passed_count += 1
            print(f"[{idx:2d}/{total_stages}] {stage_title:<34} | [{status_str}] {clear_tick:3d}틱 ({clear_tick*0.016:.2f}s) | X={final_st['x']:5.1f} | 소요={elapsed:.2f}s")
            saved_routes[map_filename] = {
                "title": stage_title,
                "strategy": strategy,
                "clear_tick": clear_tick,
                "final_x": final_st["x"],
                "final_y": final_st["y"],
            }
        else:
            print(f"[{idx:2d}/{total_stages}] {stage_title:<34} | [{status_str}] 돌파 실패 | X={final_st['x']:5.1f}, Y={final_st['y']:5.1f}")

        # Append to log file
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"| 물리커리큘럼_{idx:02d} | {map_filename} ({stage_title}) | 1 | {final_st['x']:.1f}px | [{'성공' if ok else '실패'}] | {clear_tick}틱 | 0.0 | 전략={strategy} |\n")
        except Exception:
            pass

    # Save routes
    ROUTES_FILE.write_text(json.dumps(saved_routes, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 82)
    print(f"  최종 학습 및 검증 결과: {passed_count}/{total_stages} 전수 클리어 ({passed_count/total_stages*100:.1f}%)")
    print(f"  최적 경로 저장 완료: {ROUTES_FILE}")
    print("=" * 82)


if __name__ == "__main__":
    main()
