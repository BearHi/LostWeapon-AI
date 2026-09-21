"""One-window launcher for LostWeapon native testing and local learning."""
from pathlib import Path
import json
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from snapshot_selector import snapshot_for_map

ROOT = Path(__file__).resolve().parent
FOLDER_OUTPUT = ROOT / "checkpoints" / "physics_first_local"
COMBAT_CANDIDATE = ROOT / "checkpoints" / "combat_user_selected.pt"
COMBAT_CANDIDATE_LOG = ROOT / "checkpoints" / "combat_user_selected.jsonl"
COMBAT_STOP = ROOT / "checkpoints" / "combat_curriculum.stop"
CREATE_NEW_CONSOLE = 0x10
CREATE_NO_WINDOW = 0x08000000
processes = {}
human_record_stop = None
human_record_path = None
human_record_status = None
PYTHON = sys.executable.replace("pythonw.exe", "python.exe")

root = tk.Tk(); root.title("LostWeapon Native AI Control Center")
root.geometry("700x750"); root.configure(bg="#18212e")


def launch(name, command, console=False, output_log=None):
    old = processes.get(name)
    if old and old.poll() is None:
        messagebox.showinfo("실행 중", f"{name}은 이미 실행 중입니다.")
        return
    flags = CREATE_NEW_CONSOLE if console else CREATE_NO_WINDOW
    stream = None
    try:
        if output_log is not None:
            Path(output_log).parent.mkdir(parents=True, exist_ok=True)
            stream = Path(output_log).open("ab")
        processes[name] = subprocess.Popen(
            command, cwd=ROOT, creationflags=flags,
            stdout=stream if stream is not None else None,
            stderr=subprocess.STDOUT if stream is not None else None)
    finally:
        if stream is not None:
            stream.close()


def combat_train(use_lmf=False):
    old = processes.get("칼전 학습")
    if old and old.poll() is None:
        messagebox.showinfo("실행 중", "칼전 학습이 이미 실행 중입니다.")
        return
    maps = ()
    if use_lmf:
        maps = filedialog.askopenfilenames(
            title="학습할 칼전 LMF 선택 (여러 개 선택 가능)",
            initialdir=str(ROOT.parent / "훈련용맵"),
            filetypes=(("LostWeapon map", "*.LMF"), ("All files", "*.*")))
        if not maps:
            return
    episodes = simpledialog.askinteger("지형+칼전 학습" if use_lmf else "칼전 기초 평지 학습",
                                       "맵당 추가 episode 수 (중지 후 이어서 가능)",
                                       initialvalue=20, minvalue=1, maxvalue=100000)
    if not episodes:
        return
    rounds = simpledialog.askinteger("학습 순환", "선택한 맵 목록을 몇 번 순환할까요?",
                                     initialvalue=1, minvalue=1, maxvalue=10000)
    if not rounds:
        return
    view_size = simpledialog.askinteger(
        "판단 범위", "주변 지형을 볼 홀수 칸 수 (9, 11, 13 권장)",
        initialvalue=9, minvalue=5, maxvalue=21)
    if view_size is None:
        return
    if view_size % 2 == 0:
        messagebox.showerror("판단 범위", "중앙에 캐릭터가 오도록 홀수를 선택하세요.")
        return
    COMBAT_STOP.unlink(missing_ok=True)
    command = [PYTHON, "-u", "run_combat_curriculum.py",
               "--rounds", str(rounds), "--episodes-per-stage", str(episodes),
               "--max-steps", "256", "--stop-file", str(COMBAT_STOP),
               "--view-size", str(view_size), "--checkpoint", str(COMBAT_CANDIDATE),
               "--log", str(COMBAT_CANDIDATE_LOG)]
    if maps:
        command += ["--no-flat", "--maps", *maps]
    launch("칼전 학습", command, True)


def map_train():
    lmf = filedialog.askopenfilename(
        title="학습할 LostWeapon LMF 선택",
        initialdir=str(ROOT.parent / "훈련용맵"),
        filetypes=(("LostWeapon map", "*.LMF"), ("All files", "*.*")))
    if not lmf:
        return
    episodes = simpledialog.askinteger(
        "LMF 짧은 검증 학습",
        "현재는 1~5회만 권장합니다. 추가 episode 수",
        initialvalue=3, minvalue=1, maxvalue=20)
    if episodes:
        launch("맵 클리어 학습", [PYTHON, "train_local_dqn.py",
               str(snapshot_for_map(ROOT, Path(lmf))), lmf,
               "--episodes", str(episodes), "--max-steps", "1500",
               "--action-repeat", "2", "--checkpoint",
               str(ROOT / "checkpoints" / "map_clear_shared_dqn.pt"),
               "--resume", "--skill-search"], True)


def folder_train():
    old = processes.get("폴더 자동 학습")
    if old and old.poll() is None:
        messagebox.showinfo("실행 중", "폴더 자동 학습이 이미 실행 중입니다.")
        return
    status_path = FOLDER_OUTPUT / "status.json"
    if status_path.exists():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
            if (previous.get("state") == "running" and
                    time.time() - previous.get("updated_at", 0) < 15):
                messagebox.showinfo("실행 중", "폴더 자동 학습이 다른 창에서 실행 중입니다.")
                return
        except (OSError, json.JSONDecodeError):
            pass
    folder = filedialog.askdirectory(title="자동 학습할 LMF 폴더 선택",
                                     initialdir=str(ROOT.parent / "훈련용맵"))
    if folder:
        FOLDER_OUTPUT.mkdir(parents=True, exist_ok=True)
        (FOLDER_OUTPUT / "stop.requested").unlink(missing_ok=True)
        launch("폴더 자동 학습", [PYTHON, "-u", "run_overnight_candidate.py",
               "--folder", folder, "--output", str(FOLDER_OUTPUT),
               "--episodes-per-map", "3", "--stop-on-clear"],
               output_log=FOLDER_OUTPUT / "launcher.log")


def physics_solve():
    lmf = filedialog.askopenfilename(
        title="원본 물리로 풀 LMF 선택",
        initialdir=str(ROOT.parent / "훈련용맵"),
        filetypes=(("LostWeapon map", "*.LMF"), ("All files", "*.*")))
    if lmf:
        launch("물리 경로 탐색", [PYTHON, "solve_map_physics.py", lmf,
               "--status", str(ROOT / "checkpoints" / "physics_solver_status.json")], True)


def combat_watch():
    checkpoint = COMBAT_CANDIDATE
    if not checkpoint.exists():
        messagebox.showerror("새 칼전 모델 없음", "먼저 칼전 학습을 실행하세요. 이전 모델은 입력 형식이 달라 보존만 했습니다.")
        return
    command = [sys.executable.replace("python.exe", "pythonw.exe"),
               "watch_combat_ai.py", "--checkpoint", str(checkpoint)]
    if COMBAT_CANDIDATE_LOG.exists():
        try:
            recent = json.loads(COMBAT_CANDIDATE_LOG.read_text(encoding="utf-8").splitlines()[-1])
            lmf = recent.get("map")
            if lmf and lmf != "flat_baseline" and Path(lmf).exists():
                command += ["--lmf", lmf]
        except (OSError, ValueError, IndexError, TypeError):
            pass
    launch("칼전 보기", command)


def combat_live_alert():
    radius = simpledialog.askinteger(
        "칼전 실시간 경계", "경고할 주변 반경(px). 실제 무기 사거리와는 별개입니다.",
        initialvalue=160, minvalue=64, maxvalue=640)
    if radius is None:
        return
    try:
        pid_text = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process Client -ErrorAction Stop | Select-Object -First 1).Id"],
            text=True, stderr=subprocess.DEVNULL).strip()
        pid = int(pid_text)
    except (OSError, subprocess.CalledProcessError, ValueError):
        messagebox.showerror("클라이언트 없음", "Client.exe를 켠 뒤 다시 눌러주세요.")
        return
    launch("칼전 실시간 경계", [PYTHON, "-u", "combat_live_advisor.py",
                           "--pid", str(pid), "--seconds", "3600",
                           "--alert-radius", str(radius)], True)


def record_my_play():
    global human_record_stop, human_record_path, human_record_status
    process = processes.get("내 플레이 기록")
    if process and process.poll() is None:
        messagebox.showinfo("기록 중", "이미 기록 중입니다. 게임으로 돌아가서 플레이하세요.")
        return
    folder = ROOT / "evidence" / "human_play"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    human_record_path = folder / f"human_{stamp}_{time.time_ns() % 1000000:06d}.jsonl"
    human_record_stop = human_record_path.with_suffix(".stop")
    human_record_status = human_record_path.with_suffix(".status.json")
    launch("내 플레이 기록", [PYTHON, "human_play_recorder.py", "--output",
                         str(human_record_path), "--stop-file", str(human_record_stop),
                         "--status-file", str(human_record_status),
                         "--lmf-dir", str(ROOT.parent / "훈련용맵")])
    messagebox.showinfo("내 플레이 기록", "30초 안에 Client.exe 게임 창으로 전환하세요.\n"
                        "게임 창이 앞에 있을 때만 이동·공격 키와 상태를 기록합니다.\n"
                        "여러 맵을 이어서 해도 됩니다. 전부 끝나면 중지를 누르세요.")


def stop_my_play():
    if human_record_stop is not None:
        human_record_stop.touch()
    if human_record_path is not None:
        messagebox.showinfo("기록 저장", f"저장 경로:\n{human_record_path}\n"
                            "이 기록은 아직 자동 학습에 투입되지 않습니다.")


def mark_my_play():
    if human_record_path is None or not human_record_path.exists():
        messagebox.showinfo("구간 메모", "먼저 기록을 시작하세요.")
        return
    note = simpledialog.askstring("구간 메모", "방금 한 맵과 결과를 적어주세요. 예: 훈3 클리어")
    if note:
        marker = human_record_path.with_suffix(".markers.jsonl")
        with marker.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"wall_time": time.time(), "note": note},
                                    ensure_ascii=False) + "\n")


def stop(name):
    if name == "폴더 자동 학습":
        FOLDER_OUTPUT.mkdir(parents=True, exist_ok=True)
        (FOLDER_OUTPUT / "stop.requested").touch()
        return
    if name == "칼전 학습":
        COMBAT_STOP.parent.mkdir(parents=True, exist_ok=True)
        COMBAT_STOP.touch()
        return
    process = processes.get(name)
    if process and process.poll() is None:
        process.terminate()


def refresh():
    rows = []
    physics_path = ROOT / "checkpoints" / "physics_solver_status.json"
    if physics_path.exists():
        try:
            physics = json.loads(physics_path.read_text(encoding="utf-8"))
            if physics.get("state") == "complete":
                outcome = "도달·재실행 성공" if physics.get("solved") else "이번 탐색 미해결"
                rows += [f"물리 탐색: {Path(physics['map']).stem}  {outcome}",
                         f"검증 경로 {physics.get('route_steps', 0)}결정  시도 {len(physics.get('trials', []))}개", ""]
            elif physics.get("state") == "running":
                process = processes.get("물리 경로 탐색")
                phase = "실행 중" if process and process.poll() is None else "중단됨"
                trial = physics.get("trial") or {}
                rows += [f"물리 탐색: {Path(physics['map']).stem}  {phase}",
                         f"현재 단계: {physics.get('phase')}  최근 후보: {trial.get('reason', '준비 중')}", ""]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if human_record_status is not None and human_record_status.exists():
        try:
            rec = json.loads(human_record_status.read_text(encoding="utf-8"))
            phase = {"waiting": "게임 창 대기", "recording": "기록 중",
                     "paused_other_window": "다른 창: 자동 일시정지",
                     "no_client": "게임 창을 못 찾아 종료", "ended": "기록 종료"}.get(rec.get("phase"), "상태 확인 중")
            player = rec.get("last_player") or {}
            pos = player.get("pos") or []
            position = f"  위치 ({pos[0]:.1f}, {pos[1]:.1f})" if len(pos) == 2 else ""
            rows += [f"내 플레이: {phase}  저장 {rec.get('samples', 0)}샘플",
                     f"맵 {rec.get('map_name') or '미확인'}  시도 {rec.get('attempt', '?')}  방 {player.get('room', '?')}{position}",
                     f"기록: {Path(rec.get('output', '')).name}", ""]
        except (OSError, ValueError, TypeError):
            pass
    runtime = ROOT / "checkpoints/combat_runtime_status.json"
    live = None
    if runtime.exists():
        try: live = json.loads(runtime.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError): pass
    if (live and live.get("state") == "running" and
            time.time() - live.get("updated_at", 0) < 10):
        percent = float(live.get("progress_percent", 0))
        progress["value"] = percent
        rows += [f"현재 학습: episode {live['episode']}   tick {live['tick']}/{live['max_steps']}   {percent:.1f}%",
                 f"실행 속도: {live.get('tps',0)} tick/s   현재 HP: {live.get('hp')}",
                 f"현재 행동: {live.get('actions','준비 중')}", ""]
    else:
        progress["value"] = 0
    map_runtime = ROOT / "checkpoints/map_runtime_status.json"
    map_live = None
    if map_runtime.exists():
        try: map_live = json.loads(map_runtime.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError): pass
    if (map_live and map_live.get("state") == "running" and
            time.time() - map_live.get("updated_at", 0) < 10):
        percent = float(map_live.get("progress_percent", 0))
        progress["value"] = percent
        rows = [f"맵 학습 중: {Path(map_live['map']).stem}   episode {map_live['episode']}",
                f"현재 episode: tick {map_live['tick']}/{map_live['max_steps']}   {percent:.1f}%",
                f"속도: {map_live.get('tps',0)} 결정/s   누적 보상: {map_live.get('reward',0)}",
                f"현재 위치: {map_live.get('position','준비 중')}   탐험률: {map_live.get('epsilon')}", ""] + rows
    elif (map_live and map_live.get("state") == "planning" and
          time.time() - map_live.get("updated_at", 0) < 30):
        phase = "기존 기술 재검증" if map_live.get("phase") == "skill_replay" else "새 발판 탐색"
        rows = [f"맵 학습 중: {Path(map_live['map']).stem}   {phase}",
                f"native 검사 {map_live.get('native_checks', 0)}회   깊이 {map_live.get('depth', 0)}   경과 {map_live.get('elapsed_seconds', 0)}초",
                f"목표 발판: {map_live.get('target', '계산 중')}", ""] + rows
    elif (map_live and map_live.get("state") == "crashed" and
          time.time() - map_live.get("updated_at", 0) < 300):
        rows = [f"맵 학습 오류: {map_live.get('error', '원인 기록됨')}",
                f"오류 기록: {map_live.get('crash_log', '')}", ""] + rows
    elif map_live and map_live.get("state") == "episode_complete":
        outcome = "클리어 성공" if map_live.get("success") else "이번 episode 실패"
        rows = [f"최근 맵 학습 완료: {Path(map_live['map']).stem}   episode {map_live['episode']}",
                f"결과: {outcome}   {map_live.get('steps', 0)}결정   보상 {map_live.get('reward', 0)}",
                "결과와 체크포인트는 자동 저장됨", ""] + rows
    folder_status = FOLDER_OUTPUT / "status.json"
    folder_live = None
    if folder_status.exists():
        try: folder_live = json.loads(folder_status.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError): pass
    folder_process = processes.get("폴더 자동 학습")
    folder_running = bool(folder_process and folder_process.poll() is None)
    folder_fresh = bool(folder_live and
                        time.time() - folder_live.get("updated_at", 0) < 30)
    if folder_live and folder_live.get("state") == "running" and folder_fresh:
        detail = None
        detail_path = FOLDER_OUTPUT / "map_runtime_status.json"
        if detail_path.exists():
            try: detail = json.loads(detail_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError): pass
        lines = [f"폴더 학습: {Path(folder_live['map']).stem}  "
                 f"{folder_live.get('pass', 1)}/{folder_live.get('target_passes', 3)}회",
                 f"완료 {folder_live.get('completed_maps', 0)}/{folder_live.get('playable', '?')}맵  "
                 f"목표 도달 {folder_live.get('success_maps', 0)}맵  "
                 f"남음 {folder_live.get('pending', '?')}맵"]
        if detail and detail.get("map") == str(Path(folder_live["map"]).resolve()):
            if detail.get("state") == "running":
                lines.append(f"현재 {detail.get('tick', 0)}/{detail.get('max_steps', '?')}결정  "
                             f"보상 {detail.get('reward', 0)}  "
                             f"속도 {detail.get('tps', 0)}결정/s")
                progress["value"] = float(detail.get("progress_percent", 0))
            elif detail.get("state") == "planning":
                lines.append(f"물리 경로 계산 중: {detail.get('phase', '탐색')}  "
                             f"native 검사 {detail.get('native_checks', 0)}회")
        rows = lines + [""] + rows
    elif folder_live and folder_live.get("state") == "complete":
        rows = [f"폴더 학습 완료: {folder_live.get('success_maps', 0)}/"
                f"{folder_live.get('playable', 0)}맵 목표 영역 도달  "
                f"실행 오류 {len(folder_live.get('failed', {}))}맵", ""] + rows
    elif folder_live and folder_live.get("state") == "stopped":
        rows = ["폴더 학습 중지됨: 같은 버튼을 누르면 이어서 실행", ""] + rows
    elif folder_live and folder_live.get("state") == "crashed":
        rows = [f"폴더 학습 오류: {folder_live.get('error', '기록 확인')}",
                f"자세한 기록: {FOLDER_OUTPUT / 'launcher.log'}", ""] + rows
    elif folder_live and folder_live.get("state") == "running" and not folder_running:
        rows = ["폴더 학습 중단됨: 같은 버튼을 누르면 이어서 실행", ""] + rows
    log = (COMBAT_CANDIDATE_LOG if COMBAT_CANDIDATE_LOG.exists()
           else ROOT / "checkpoints/combat_training.jsonl")
    if log.exists():
        parsed = []
        for line in log.read_text(encoding="utf-8").splitlines():
            try: parsed.append(json.loads(line))
            except json.JSONDecodeError: pass
        if parsed:
            last = parsed[-1]
            rows += [f"칼전 누적 episode: {last['episode']}",
                     f"최근 HP: {last['hp']}    보상: {last['reward0']}, {last['reward1']}",
                     f"탐험률 epsilon: {last['epsilon']}    시작 거리: {last['spawn_gap']}"]
    if not rows: rows.append("아직 유효한 칼전 학습 기록이 없습니다.")
    rows.append("")
    for name in ("칼전 학습", "칼전 보기", "맵 물리 테스트", "맵 클리어 학습", "폴더 자동 학습", "내 플레이 기록", "물리 경로 탐색"):
        p = processes.get(name)
        externally_active = (name == "폴더 자동 학습" and folder_live and
                             folder_live.get("state") == "running" and folder_fresh)
        state = "실행 중" if (p and p.poll() is None) or externally_active else "정지"
        rows.append(f"{name}: {state}")
    status.config(text="\n".join(rows))
    root.after(2000, refresh)


title = tk.Label(root, text="LostWeapon Native AI", bg="#18212e", fg="white",
                 font=("Segoe UI", 20, "bold")); title.pack(pady=(18, 8))
buttons = tk.Frame(root, bg="#18212e"); buttons.pack(pady=8)
style = {"width": 23, "height": 1, "font": ("Segoe UI", 11), "bd": 0}
tk.Button(buttons, text="칼전 기초 평지 학습", command=combat_train, bg="#32b6d8", **style).grid(row=0,column=0,padx=6,pady=6)
tk.Button(buttons, text="학습한 칼전 보기", command=combat_watch, bg="#ef6681", **style).grid(row=0,column=1,padx=6,pady=6)
tk.Button(buttons, text="LMF 맵 물리 테스트", command=lambda: launch(
    "맵 물리 테스트", [sys.executable.replace("python.exe","pythonw.exe"), "native_playground.py"]),
    bg="#e0a94c", **style).grid(row=1,column=0,padx=6,pady=6)
tk.Button(buttons, text="LMF 짧은 검증 학습", command=map_train,
    bg="#65c995", **style).grid(row=1,column=1,padx=6,pady=6)
tk.Button(buttons, text="칼전 학습 중지", command=lambda: stop("칼전 학습"), bg="#788598", **style).grid(row=2,column=0,padx=6,pady=6)
tk.Button(buttons, text="칼전 보기 닫기", command=lambda: stop("칼전 보기"), bg="#788598", **style).grid(row=2,column=1,padx=6,pady=6)
tk.Button(buttons, text="맵 학습 중지", command=lambda: stop("맵 클리어 학습"), bg="#788598", **style).grid(row=3,column=0,columnspan=2,padx=6,pady=6)
tk.Button(buttons, text="폴더 자동 학습", command=folder_train, bg="#65c995", **style).grid(row=4,column=0,padx=6,pady=6)
tk.Button(buttons, text="폴더 학습 중지", command=lambda: stop("폴더 자동 학습"), bg="#788598", **style).grid(row=4,column=1,padx=6,pady=6)
tk.Button(buttons, text="내 플레이 기록", command=record_my_play, bg="#32b6d8", **style).grid(row=5,column=0,padx=6,pady=6)
tk.Button(buttons, text="내 플레이 기록 중지", command=stop_my_play, bg="#788598", **style).grid(row=5,column=1,padx=6,pady=6)
tk.Button(buttons, text="방금 한 맵 메모", command=mark_my_play, bg="#e0a94c", **style).grid(row=6,column=0,padx=6,pady=6)
tk.Button(buttons, text="물리로 맵 풀기", command=physics_solve, bg="#65c995", **style).grid(row=6,column=1,padx=6,pady=6)
tk.Button(buttons, text="물리 탐색 중지", command=lambda: stop("물리 경로 탐색"), bg="#788598", **style).grid(row=7,column=1,padx=6,pady=6)
tk.Button(buttons, text="LMF 지형+칼전 학습", command=lambda: combat_train(True),
          bg="#32b6d8", **style).grid(row=7,column=0,padx=6,pady=6)
tk.Button(buttons, text="칼전 실시간 경계", command=combat_live_alert,
          bg="#e0a94c", **style).grid(row=8,column=0,padx=6,pady=6)
tk.Button(buttons, text="칼전 경계 닫기", command=lambda: stop("칼전 실시간 경계"),
          bg="#788598", **style).grid(row=8,column=1,padx=6,pady=6)

status = tk.Label(root, text="", justify="left", anchor="nw", bg="#111925", fg="#dbe8f4",
                  font=("Consolas", 11), padx=14, pady=12)
status.pack(fill="both", expand=True, padx=22, pady=12)
progress = ttk.Progressbar(root, orient="horizontal", mode="determinate", maximum=100)
progress.pack(fill="x", padx=22, pady=(0,8))
tk.Label(root, text="물리 경로 탐색은 오프라인 원본 x86 목표 접촉 검증입니다. 온라인 클리어와는 별개입니다.",
         bg="#18212e", fg="#ffcf70", font=("Segoe UI", 10)).pack(pady=(0,12))
refresh(); root.mainloop()
