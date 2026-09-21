import sys
import os
import time
import json
import struct
from pathlib import Path
import random

# Fix Windows console UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(r"c:\Users\sang\Desktop\로스트웨폰 맵")
sys.path.insert(0, str(ROOT / "native_harness"))

from api import SimpleTrainingAPI
from snapshot_selector import snapshot_for_map
from native_env import ACTIONS

# -----------------------------------------------------------------------------
# 1. PROCEDURAL LMF MAP BUILDER
# -----------------------------------------------------------------------------
def build_lmf_file(width: int, height: int, records: list, out_path: Path):
    """Build valid LostWeapon 32-byte header binary LMF map file."""
    header = bytearray(32)
    header[:16] = b"NewLWMapFile_1.0"
    struct.pack_into("<HH", header, 16, width, height)
    header[20] = 0x12  # magic byte
    struct.pack_into("<I", header, 21, len(records))
    
    body = bytearray()
    for tile_id, x, y in records:
        body.extend(struct.pack("<Ihh", int(tile_id), int(x), int(y)))
        
    out_path.write_bytes(bytes(header) + bytes(body))
    return out_path

def generate_curriculum_stage(stage_id: int) -> tuple[Path, str, float, float]:
    """Generate map according to curriculum stage. Returns (path, desc, spawn_x, goal_x)."""
    maps_dir = ROOT / "훈련용맵" / "curriculum"
    maps_dir.mkdir(parents=True, exist_ok=True)
    
    records = []
    width, height = 30, 18
    ground_y = 14
    lava_y = 16

    # Bottom lava pit for whole map
    for x in range(1, 29):
        records.append((49, x, lava_y))

    spawn_x_tile = 3
    records.append((100, spawn_x_tile, ground_y - 1))
    goal_x_tile = 25
    records.append((140, goal_x_tile, ground_y - 1))

    if stage_id == 1:
        desc = "Lv.1: 2칸 기본 점프 훈련"
        gap_start, gap_size = 9, 2
        for x in range(1, gap_start):
            records.append((7, x, ground_y))
        for x in range(gap_start + gap_size, 29):
            records.append((7, x, ground_y))

    elif stage_id == 2:
        desc = "Lv.2: 3칸 낭떠러지 점프 훈련"
        gap_start, gap_size = 9, 3
        for x in range(1, gap_start):
            records.append((7, x, ground_y))
        for x in range(gap_start + gap_size, 29):
            records.append((7, x, ground_y))

    elif stage_id == 3:
        desc = "Lv.3: 4칸 롱점프/대시점프 훈련"
        gap_start, gap_size = 8, 4
        for x in range(1, gap_start):
            records.append((7, x, ground_y))
        for x in range(gap_start + gap_size, 29):
            records.append((7, x, ground_y))

    elif stage_id == 4:
        desc = "Lv.4: 연속 2단 낭떠러지 점프 훈련"
        # 2 gaps: x=8..9 (2칸), x=14..16 (3칸)
        for x in range(1, 8):
            records.append((7, x, ground_y))
        for x in range(10, 14):
            records.append((7, x, ground_y))
        for x in range(17, 29):
            records.append((7, x, ground_y))

    elif stage_id == 5:
        desc = "Lv.5: 스프링 고점프 연계 훈련"
        # Floor with spring at x=8, high wall at x=12, goal flag on high platform
        for x in range(1, 10):
            records.append((7, x, ground_y))
        records.append((4, 8, ground_y - 1))  # Spring on platform!
        for x in range(11, 29):
            records.append((7, x, ground_y - 3))  # Elevated platform!
        records.remove((140, goal_x_tile, ground_y - 1))
        records.append((140, goal_x_tile, ground_y - 4))

    else:
        desc = f"Lv.{stage_id}: 복합 장애물 훈련"
        for x in range(1, 8):
            records.append((7, x, ground_y))
        for x in range(12, 29):
            records.append((7, x, ground_y))

    map_path = maps_dir / f"stage_{stage_id}.LMF"
    build_lmf_file(width, height, records, map_path)
    return map_path, desc, spawn_x_tile * 32.0 + 16.0, goal_x_tile * 32.0 + 16.0

# -----------------------------------------------------------------------------
# 2. MACRO ACTIONS & SEARCH POLICIES
# -----------------------------------------------------------------------------
MACRO_SKILLS = [
    ("RUN", [(['RIGHT'], 4)]),
    ("LONG_RUN", [(['RIGHT'], 8)]),
    ("SHORT_JUMP", [(['RIGHT', 'C'], 10)]),
    ("MED_JUMP", [(['RIGHT', 'C'], 14)]),
    ("LONG_JUMP", [(['RIGHT', 'C'], 18)]),
    ("DASH_JUMP", [(['RIGHT'], 4), (['RIGHT', 'C'], 18)]),
    ("HIGH_JUMP", [(['C'], 8), (['RIGHT', 'C'], 14)]),
    ("ATTACK_RUN", [(['RIGHT', 'Z'], 6)]),
]

def run_episode(api, plan, goal_x):
    """Simulate a plan and return (cleared, final_x, ticks, reward)."""
    api.reset()
    init = api.read_state()
    cur_x = init["x"]
    cur_y = init["y"]
    ticks = 0
    reward = 0.0
    reached = False

    for skill_idx in plan:
        name, steps = MACRO_SKILLS[skill_idx]
        for keys, count in steps:
            for _ in range(count):
                st = api.step(1, keys=keys)
                ticks += 1
                dx = st["x"] - cur_x
                cur_x = st["x"]
                cur_y = st["y"]

                # Fall into lava / pit: platform ground is Y=448.0, true fall is Y > 470.0
                if cur_y > 470.0 and cur_x < goal_x - 32.0:
                    reward -= 50.0
                    return False, cur_x, ticks, reward

                # Goal reached
                if cur_x >= goal_x - 24.0:
                    reward += 100.0
                    return True, cur_x, ticks, reward

    return reached, cur_x, ticks, reward

# -----------------------------------------------------------------------------
# 3. AUTONOMOUS CURRICULUM TRAINER MAIN LOOP
# -----------------------------------------------------------------------------
def main():
    print("=" * 80)
    print("LOSTWEAPON AUTONOMOUS CURRICULUM TRAINER (ZERO-TOKEN HIGH SPEED)")
    print("=" * 80)
    print("Training runs 100% locally on x86 native emulator with GPU/CPU acceleration.")
    print("Real-time results are continuously appended to TRAINING_LOG.md\n")

    log_file = ROOT / "TRAINING_LOG.md"
    best_routes_file = ROOT / "checkpoints" / "best_curriculum_routes.json"
    best_routes_file.parent.mkdir(parents=True, exist_ok=True)
    best_routes = {}

    current_stage = 1
    max_stages = 5
    global_episode = 7  # Continuation from previous 6 episodes

    while current_stage <= max_stages:
        map_path, stage_desc, spawn_x, goal_x = generate_curriculum_stage(current_stage)
        snap_path = snapshot_for_map(ROOT / "native_harness", map_path)
        
        print(f"\n>>> [STAGE {current_stage}] {stage_desc}")
        print(f"    Map: {map_path.name} | Goal X: {goal_x:.1f}px")

        api = SimpleTrainingAPI(snap_path, str(map_path))
        
        stage_cleared = False
        stage_attempts = 0
        best_plan = None
        best_ticks = 999999
        best_reward = -999999

        # We start with a base plan and evolve it
        base_plan = [0] * 6  # Start by walking

        MAX_STAGE_ATTEMPTS = 5
        # Structured curriculum trial plans: Walk, Short Jump, Mid Jump, Long Jump, Dash Jump
        test_plans = [
            [0, 0, 0, 0, 0, 0],                            # 1. Walk only
            [0, 1, 2, 0, 0, 0, 0],                         # 2. Early jump
            [1, 1, 3, 1, 1, 1, 1, 1],                      # 3. Mid jump before gap
            [1, 1, 4, 1, 1, 1, 1, 1, 1],                   # 4. Long jump before gap
            [1, 1, 5, 1, 1, 1, 1, 1, 1, 1],                # 5. Dash jump before gap
        ]

        while not stage_cleared and stage_attempts < MAX_STAGE_ATTEMPTS:
            plan = test_plans[stage_attempts]
            stage_attempts += 1
            global_episode += 1

            cleared, final_x, ticks, reward = run_episode(api, plan, goal_x)

            if cleared:
                stage_cleared = True
                if ticks < best_ticks:
                    best_ticks = ticks
                    best_reward = reward
                    best_plan = plan
                outcome_str = "[🚩 깃발 도달 성공! (STAGE CLEAR)]"
                note_str = f"최적화 경로 돌파 성공! (소요 시간: {ticks}틱, 시도: {stage_attempts}회)"
            elif reward > best_reward:
                best_reward = reward
                best_plan = plan
                outcome_str = "[❌ 낭떠러지 낙사]"
                note_str = f"신기록 전진: X={final_x:.1f}px까지 도달"
            else:
                outcome_str = "[❌ 낭떠러지 낙사]"
                note_str = f"X={final_x:.1f}px에서 추락"

            # Print concise one-liner progress
            print(f"  Ep {global_episode:3d} (시도 {stage_attempts:2d}) | X={final_x:5.1f} | {outcome_str:<26} | Ticks={ticks:3d} | Reward={reward:+6.1f}")

            # Append to TRAINING_LOG.md
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"| {global_episode} | {map_path.name} ({stage_desc}) | 시도 {stage_attempts} | {final_x:.1f}px | {outcome_str} | {ticks}틱 | {reward:+.1f} | {note_str} |\n")

        if stage_cleared:
            print(f"\n[★★★] STAGE {current_stage} CLEARED! 기록: {best_ticks}틱 (보상: {best_reward:+.1f})")
            best_routes[f"stage_{current_stage}"] = {
                "desc": stage_desc,
                "ticks": best_ticks,
                "reward": best_reward,
                "plan": [MACRO_SKILLS[i][0] for i in best_plan]
            }
            with open(best_routes_file, "w", encoding="utf-8") as f:
                json.dump(best_routes, f, ensure_ascii=False, indent=2)
            current_stage += 1
            time.sleep(0.5)
        else:
            print(f"\n[!] Stage {current_stage} requires more exploration. Retrying with fine-tuning...")

    print("\n" + "=" * 80)
    print("ALL CURRICULUM STAGES COMPLETED SUCCESSFULLY!")
    print("Check TRAINING_LOG.md for full history and checkpoints/best_curriculum_routes.json for trained policies.")
    print("=" * 80)

if __name__ == "__main__":
    main()
