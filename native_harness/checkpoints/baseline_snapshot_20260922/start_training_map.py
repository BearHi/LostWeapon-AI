"""Pick an arbitrary LMF and start local training in a separate console."""
from pathlib import Path
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from snapshot_selector import snapshot_for_map

HARNESS = Path(__file__).resolve().parent
root = tk.Tk()
root.withdraw()
lmf = filedialog.askopenfilename(
    title="학습할 LostWeapon LMF 선택",
    initialdir=r"C:\Users\microsoft\Downloads\NewLostweapon\Map",
    filetypes=(("LostWeapon map", "*.LMF"), ("All files", "*.*")),
)
if not lmf:
    raise SystemExit(0)
episodes = simpledialog.askinteger(
    "로컬 짧은 검증 학습", "현재는 1~5회만 권장합니다. episode 수",
    initialvalue=3, minvalue=1, maxvalue=20)
if episodes is None:
    raise SystemExit(0)
# Every selected map continues one navigation/object policy. Map identity and
# physics fingerprints remain recorded in the episode archive.
checkpoint = HARNESS / "checkpoints" / "map_clear_shared_dqn.pt"
python = sys.executable.replace("pythonw.exe", "python.exe")
command = [python, str(HARNESS / "train_local_dqn.py"),
           str(snapshot_for_map(HARNESS, Path(lmf))), lmf,
           "--episodes", str(episodes), "--max-steps", "1500",
           "--action-repeat", "2", "--checkpoint", str(checkpoint), "--resume"]
command.append("--skill-search")
try:
    subprocess.Popen(command, cwd=HARNESS,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
except Exception as exc:
    messagebox.showerror("학습 실행 실패", f"{type(exc).__name__}: {exc}")
    raise
messagebox.showinfo("로컬 학습", f"학습을 시작했습니다.\n체크포인트: {checkpoint}")
