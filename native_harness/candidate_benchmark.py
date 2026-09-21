"""Frozen counterfactual candidate comparison using existing native trial results.

Not a fresh gameplay/Client evaluation. A group shares map, exact replay prefix,
context, and execution budget; only recorded planned candidates are compared.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import numpy as np
import torch


def create_benchmark(source,path,per_map=128):
    from shared_physics_model import HOLDOUT_MAPS,ROOT
    from training_archive import physics_fingerprint
    physics=physics_fingerprint(ROOT)
    if path.exists():
        saved=json.loads(path.read_text(encoding="utf-8"))
        if saved["physics"]!=physics:raise ValueError("frozen benchmark physics mismatch")
        return saved
    cases=[]
    for name in sorted(HOLDOUT_MAPS):
        database=source/(name+".sqlite3")
        if not database.exists():continue
        db=sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True)
        try:
            identity=json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
            if identity["physics"]!=physics:raise ValueError("benchmark source physics mismatch")
            contexts=dict(db.execute("SELECT key,value FROM contexts"));groups=defaultdict(dict)
            for raw, in db.execute("SELECT result FROM trials WHERE mode='search' ORDER BY id"):
                r=json.loads(raw)
                if not r.get("planned_phases") or not 0<r.get("plan_budget",10000)<=64:continue
                if r["reason"] not in ("horizon","stalled","goal_region","reset_suspected","out_of_bounds"):continue
                key=json.dumps([r["context"],r["prefix"],r["plan_budget"]],sort_keys=True)
                plan=json.dumps(r["planned_phases"])
                groups[key].setdefault(plan,r)
            eligible=[(hashlib.sha256((name+key).encode()).hexdigest(),key,rows)
                      for key,rows in groups.items() if len(rows)>=4]
            for _,key,rows in sorted(eligible)[:per_map]:
                selected=list(rows.values())[:8];r=selected[0]
                context=json.loads(contexts[r["context"]])
                goal=np.asarray(context["goal_delta"],dtype=float)
                direction=goal/max(np.linalg.norm(goal),1)
                candidates=[]
                for row in selected:
                    risk=int(row["reason"] in ("reset_suspected","out_of_bounds"))
                    delta=[(row["after"][k]-row["before"][k])/128 for k in ("x","y")]
                    duration=sum(n for a,n in row["actions"])/64
                    candidates.append({"family":row["family"],"plan":row["planned_phases"],
                        "risk":risk,"utility":float(np.clip(np.dot(delta,direction),-2,2)-3*risk-.05*min(1,duration))})
                cases.append({"map":name,"key":hashlib.sha256(key.encode()).hexdigest(),
                              "context":context,"budget":r["plan_budget"],"candidates":candidates})
        finally:db.close()
    saved={"physics":physics,"cases":cases,"evidence":"recorded_native_candidates_not_fresh_gameplay"}
    if len(cases)<64:return saved  # collect more before freezing/promoting
    temp=path.with_suffix(".tmp");temp.write_text(json.dumps(saved,ensure_ascii=False),encoding="utf-8");temp.replace(path)
    return saved


def evaluate(model,benchmark,risk_weight=6):
    from shared_physics_model import features,plan_tokens
    model.eval();rows=[]
    with torch.no_grad():
        for case in benchmark["cases"]:
            candidates=case["candidates"];n=len(candidates)
            grid,obj,scalar=features(case["context"])
            plans=np.stack([plan_tokens(c["plan"],case["budget"]) for c in candidates])
            pred=model(torch.from_numpy(np.repeat(grid[None],n,0)),torch.from_numpy(np.repeat(obj[None],n,0)),
                       torch.from_numpy(np.repeat(scalar[None],n,0)),torch.from_numpy(plans)).numpy()
            d=np.asarray(case["context"]["goal_delta"],float);d/=max(np.linalg.norm(d),1)
            risk=1/(1+np.exp(-np.clip(pred[:,3],-20,20)))
            scores=np.clip(pred[:,:2]@d,-2,2)-risk_weight*risk-.05*np.clip(pred[:,2],0,1)
            chosen=candidates[int(np.argmax(scores))]
            rows.append([chosen["utility"],np.mean([c["utility"] for c in candidates]),
                         chosen["risk"],np.mean([c["risk"] for c in candidates]),
                         max(c["utility"] for c in candidates)])
    m=np.asarray(rows).mean(0) if rows else np.zeros(5)
    return dict(groups=len(rows),mean_utility=float(m[0]),random_mean_utility=float(m[1]),
                selected_reset_rate=float(m[2]),random_reset_rate=float(m[3]),
                oracle_mean_utility=float(m[4]),risk_weight=risk_weight,
                evidence="fixed_recorded_native_candidate_comparison")


def safe_to_promote(candidate,incumbent):
    """Do not exchange material safety/selection regression for lower average pixel error."""
    if candidate["groups"]<64:return False
    if candidate["selected_reset_rate"]>candidate["random_reset_rate"]+.005:return False
    if candidate["mean_utility"]<candidate["random_mean_utility"]:return False
    if incumbent is not None:
        return (candidate["selected_reset_rate"]<=incumbent["selected_reset_rate"]+.005 and
                candidate["mean_utility"]>=incumbent["mean_utility"]-.01)
    return True
