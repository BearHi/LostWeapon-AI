"""Bounded local cycle: fit pooled experience, validate, collect more native trials.

No API access. Stop is shared with the existing local training launcher.
The four held-out maps stay excluded from gradient updates across cycles.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent


def save_status(path, data):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)


def backup_once(source,out):
    marker=out/"source_backup.json"
    if marker.exists():return
    destination=out/("source_backup_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
    destination.mkdir()
    names=[]
    for path in source.glob("*.sqlite3"):
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True) as src:
            with sqlite3.connect(destination/path.name) as target:src.backup(target)
        names.append(path.name)
    if (source/"curriculum.json").exists():
        shutil.copy2(source/"curriculum.json",destination/"curriculum.json")
    save_status(marker,{"path":str(destination),"databases":names})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"checkpoints/local_physics_v1")
    p.add_argument("--out",type=Path,default=ROOT/"checkpoints/shared_physics_v1")
    p.add_argument("--hours",type=float,default=4)
    p.add_argument("--epochs",type=int,default=15)
    p.add_argument("--trials-per-map",type=int,default=64)
    p.add_argument("--minutes-per-map",type=float,default=5)
    p.add_argument("--cycles",type=int,default=100)
    p.add_argument("--maps",nargs="*",help="optional collection subset; model still uses all source maps")
    p.add_argument("--fit-only",action="store_true")
    args=p.parse_args()
    if min(args.hours,args.epochs,args.trials_per_map,args.minutes_per_map,args.cycles)<=0:
        p.error("all budgets must be positive")
    args.source=args.source.resolve();args.out=args.out.resolve()
    if not args.source.exists():p.error("source experience folder missing")
    args.out.mkdir(parents=True,exist_ok=True)
    import msvcrt
    with (args.out/"RUN.lock").open("a+b") as lock:
        lock.seek(0,2)
        if lock.tell()==0:lock.write(b"0");lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:p.error("shared learning already running")
        # Refuse to start while the previous standalone native coordinator is active.
        with (args.source/"RUN.lock").open("a+b") as native_lock:
            native_lock.seek(0,2)
            if native_lock.tell()==0:native_lock.write(b"0");native_lock.flush()
            native_lock.seek(0)
            try:msvcrt.locking(native_lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:p.error("stop the old local training first, then restart this launcher")
        stop=args.source/"STOP"
        stop.unlink(missing_ok=True)
        deadline=time.time()+args.hours*3600
        status_path=args.out/"learning_status.json"
        status={"state":"starting","deadline":deadline,"source":str(args.source)}
        save_status(status_path,status)
        try:
            backup_once(args.source,args.out)
            from shared_physics_model import fit
            for cycle in range(1,args.cycles+1):
                if stop.exists() or time.time()>=deadline:break
                status.update(state="fitting",cycle=cycle)
                save_status(status_path,status)
                result=fit(args.source,args.out,args.epochs,stop,deadline)
                status["last_fit"]={k:v for k,v in result.items() if k!="history"}
                save_status(status_path,status)
                if args.fit_only or stop.exists() or time.time()>=deadline:break
                status["state"]="collecting_native_experience"
                save_status(status_path,status)
                command=[sys.executable,"-u",str(ROOT/"local_physics_train.py"),
                         "--out",str(args.source),"--rounds","1",
                         "--trials-per-map",str(args.trials_per_map),
                         "--minutes-per-map",str(args.minutes_per_map),
                         "--hours",str(max(.0001,(deadline-time.time())/3600)),
                         "--max-nodes","12000"]
                # No adaptive shortest-record stopping. Learning gets more diverse data.
                if (args.out/"active.pt").exists():
                    command += ["--guide-model",str(args.out/"active.pt")]
                if args.maps:command += ["--maps",*args.maps]
                code=subprocess.run(command,cwd=ROOT,check=False).returncode
                if code and not stop.exists():raise RuntimeError(f"native collection failed: {code}")
            status["state"]="stopped" if stop.exists() else "time_budget_complete" if time.time()>=deadline else "cycle_budget_complete"
        except KeyboardInterrupt:
            stop.touch();status["state"]="stopped"
        except Exception as exc:
            status.update(state="error",error=repr(exc));raise
        finally:
            save_status(status_path,status)
            print(json.dumps({"phase":"shared_learning_end",**status},ensure_ascii=False),flush=True)


if __name__=="__main__":main()
