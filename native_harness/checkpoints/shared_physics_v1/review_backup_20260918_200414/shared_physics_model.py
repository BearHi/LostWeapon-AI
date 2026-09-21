"""Shared CPU outcome learner. Native simulation remains the authority.

Maps and exact-context hashes are NOT model inputs. Predict displacement,
duration and heuristic reset/out-of-bounds risk from local state + timed plan.
Old executed sequences are valid fixed-input transition examples, not labels
for the changing named templates which originally generated them.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parent
SCHEMA = "local-outcome-v1"
HOLDOUT_MAPS = {"훈3", "훈7.5", "훈13", "훈19"}
FIELDS = ("motion58", "38", "3c", "68", "74", "7c", "80", "b0", "b8", "c0", "c4", "d0", "dc")
KEYS = ("LEFT", "RIGHT", "UP", "DOWN", "C", "Z", "X", "1", "2", "3", "4")
PLAN_LENGTH = 64
PAD = 23  # original actions 0..20, conditional left/right chute 21/22
SCALARS = len(FIELDS) + 2 + len(KEYS) + 33 + 33


def emit(**row):
    print(json.dumps(row, ensure_ascii=False), flush=True)


def plan_tokens(phases, budget=64):
    tokens = []
    for spec, duration in phases:
        token = {"chute_LEFT": 21, "chute_RIGHT": 22}.get(spec, spec)
        if not isinstance(token, int) or not 0 <= token < PAD or int(duration) < 0:
            raise ValueError("invalid action plan")
        tokens.extend([token] * min(int(duration), PLAN_LENGTH-len(tokens), max(0, budget-len(tokens))))
        if len(tokens) >= min(PLAN_LENGTH, budget):
            break
    if not tokens:
        raise ValueError("empty plan")
    return np.asarray(tokens+[PAD]*(PLAN_LENGTH-len(tokens)), dtype=np.int64)


def features(context):
    grid = np.asarray([[(cell if cell is not None else [65535]*4)
                         for cell in row] for row in context["grid"]], dtype=np.float32)
    if grid.shape != (9,9,4):
        raise ValueError("expected four native grids in a 9x9 window")
    grid = np.log1p(np.clip(grid, 0, 65535))/math.log(65536)
    objects = np.zeros((9,9,4),dtype=np.int64)
    counts = np.zeros((9,9),dtype=np.int64)
    for raw, dx, dy in context.get("objects", []):
        if not (-4 <= dx <= 4 and -4 <= dy <= 4):
            continue
        x,y=int(dx)+4,int(dy)+4
        slot=counts[y,x]
        if slot < 4:
            objects[y,x,slot]=min(255,max(0,int(raw)))
            counts[y,x]+=1
    state=context["player"]
    v=np.asarray([float(state.get(k,0)) for k in FIELDS],dtype=np.float32)
    v=np.sign(v)*np.log1p(np.minimum(np.abs(v),1e6))/8
    flags=[]
    for field in ("38","c0"):
        one=np.zeros(33,dtype=np.float32)
        one[min(32,max(0,int(state.get(field,0))))]=1
        flags.extend(one)
    scalars=np.concatenate((v,np.asarray(context["subcell"],dtype=np.float32)/32,
        np.asarray([k in context.get("held",[]) for k in KEYS],dtype=np.float32),flags))
    return grid.transpose(2,0,1), objects, scalars


class OutcomeModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.objects=nn.Embedding(256,8,padding_idx=0)
        self.actions=nn.Embedding(24,8,padding_idx=PAD)
        self.terrain=nn.Sequential(nn.Conv2d(12,16,3,padding=1),nn.ReLU(),
                                  nn.Conv2d(16,16,3,stride=2,padding=1),nn.ReLU(),nn.Flatten())
        self.head=nn.Sequential(nn.Linear(16*5*5+SCALARS+64*8,128),nn.ReLU(),
                                nn.Linear(128,64),nn.ReLU(),nn.Linear(64,4))

    def forward(self,grid,objects,scalars,plan):
        obj=self.objects(objects).sum(dim=3).permute(0,3,1,2)
        terrain=self.terrain(torch.cat((grid,obj),dim=1))
        actions=self.actions(plan).flatten(1)
        return self.head(torch.cat((terrain,scalars,actions),dim=1))


def build_data(source, output):
    """Build from immutable/read-only source connections, grouping evaluation by map/context."""
    arrays=[[],[],[],[],[],[],[]]
    sources=[]; skipped=0; planned=0
    from training_archive import physics_fingerprint
    current_physics=physics_fingerprint(ROOT)
    for path in sorted(source.glob("*.sqlite3")):
        db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
        try:
            identity=json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
            if identity["physics"] != current_physics:
                raise ValueError("physics changed; replay source data before learning: "+path.name)
            contexts=dict(db.execute("SELECT key,value FROM contexts"))
            count=0
            for row_id,raw in db.execute("SELECT id,result FROM trials WHERE mode='search' ORDER BY id"):
                r=json.loads(raw)
                if "context" not in r or r["reason"] not in ("horizon","stalled","goal_region","reset_suspected","out_of_bounds"):
                    skipped+=1;continue
                length=sum(n for a,n in r["actions"])
                if not 0 < length <= PLAN_LENGTH:
                    skipped+=1;continue
                context=json.loads(contexts[r["context"]])
                if r.get("planned_phases") is not None:
                    # Long plans cannot be described faithfully by a 64-decision encoder.
                    budget=min(r.get("plan_budget",PLAN_LENGTH),sum(n for a,n in r["planned_phases"]))
                    if budget>PLAN_LENGTH:
                        skipped+=1;continue
                    plan=plan_tokens(r["planned_phases"],budget);planned+=1
                else:
                    plan=plan_tokens(r["actions"])
                grid,obj,scalar=features(context)
                risk=float(r["reason"] in ("reset_suspected","out_of_bounds"))
                target=np.asarray([(r["after"]["x"]-r["before"]["x"])/128,
                                   (r["after"]["y"]-r["before"]["y"])/128,length/64,risk],dtype=np.float32)
                if not np.all(np.isfinite(target)):
                    skipped+=1;continue
                # All candidates at one context stay on the same side of the split.
                bucket=int(hashlib.sha256((path.stem+r["context"]).encode()).hexdigest()[:8],16)%10
                split=2 if path.stem in HOLDOUT_MAPS else 1 if bucket<2 else 0
                for dest,val in zip(arrays,(grid,obj,scalar,plan,target,split,path.stem)):
                    dest.append(val)
                count+=1
            sources.append({"map":path.stem,"samples":count})
        finally:
            db.close()
    if len(arrays[0]) < 100:
        raise ValueError("not enough usable examples; collect native experience first")
    data={k:np.asarray(v) for k,v in zip(("grid","objects","scalars","plan","target","split","map"),arrays)}
    output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/"dataset.npz",**data)
    metadata={"schema":SCHEMA,"physics":current_physics,"samples":len(arrays[0]),
              "planned_samples":planned,"legacy_fixed_sequence_samples":len(arrays[0])-planned,
              "splits":{name:int((data['split']==i).sum()) for i,name in enumerate(("train","validation_contexts","heldout_maps"))},
              "heldout_maps":sorted(HOLDOUT_MAPS),"sources":sources,"skipped":skipped}
    (output/"dataset.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    emit(phase="dataset",**{k:metadata[k] for k in ("samples","planned_samples","splits")})
    return data,metadata


def tensors(data):
    return [torch.from_numpy(data[k]).to(dtype=torch.long if k in ("objects","plan") else torch.float32)
            for k in ("grid","objects","scalars","plan","target")]


def metrics(model,ts,indices,baseline):
    if len(indices)==0:
        return None
    predictions=[]
    model.eval()
    with torch.no_grad():
        for start in range(0,len(indices),512):
            ix=indices[start:start+512]
            predictions.append(model(*[t[ix] for t in ts[:4]]))
    p=torch.cat(predictions);y=ts[4][indices]
    safe=y[:,3]==0
    endpoint=float((p[safe,:2]-y[safe,:2]).abs().mean()*128) if safe.any() else None
    base_endpoint=float((baseline[:2]-y[safe,:2]).abs().mean()*128) if safe.any() else None
    risk=p[:,3].sigmoid()
    return {"samples":len(indices),"endpoint_mae_pixels":endpoint,
            "constant_endpoint_mae_pixels":base_endpoint,
            "risk_brier":float(((risk-y[:,3])**2).mean()),
            "constant_risk_brier":float(((baseline[3]-y[:,3])**2).mean()),
            "duration_mae_decisions":float((p[:,2]-y[:,2]).abs().mean()*64)}


def fit(source,output,epochs=15,stop_file=None,deadline=None):
    torch.set_num_threads(min(4,torch.get_num_threads()))
    torch.manual_seed(917)
    data,meta=build_data(source,output)
    ts=tensors(data)
    train=torch.as_tensor(np.flatnonzero(data["split"]==0))
    valid=torch.as_tensor(np.flatnonzero(data["split"]==1))
    holdout=torch.as_tensor(np.flatnonzero(data["split"]==2))
    if min(len(train),len(valid),len(holdout))<20:
        raise ValueError("need independent validation contexts AND held-out maps")
    baseline=ts[4][train].mean(0)
    safe_train=train[ts[4][train,3]==0]
    baseline[:2]=ts[4][safe_train,:2].mean(0)
    model=OutcomeModel()
    latest=output/"latest.pt"
    if latest.exists():
        old=torch.load(latest,map_location="cpu",weights_only=True)
        if old["schema"]==SCHEMA and old["physics"]==meta["physics"]:
            model.load_state_dict(old["weights"])
    optimizer=torch.optim.AdamW(model.parameters(),lr=.0005,weight_decay=.0001)
    best_loss=math.inf;best_weights=None;patience=0;history=[]
    for epoch in range(epochs):
        if (stop_file and stop_file.exists()) or (deadline and time.time()>=deadline):
            break
        model.train()
        order=train[torch.randperm(len(train))]
        for offset in range(0,len(order),256):
            if (stop_file and stop_file.exists()) or (deadline and time.time()>=deadline):
                break
            ix=order[offset:offset+256];y=ts[4][ix]
            pred=model(*[t[ix] for t in ts[:4]])
            safe=y[:,3]==0
            loss=nn.functional.binary_cross_entropy_with_logits(pred[:,3],y[:,3])
            if safe.any():
                loss=loss+nn.functional.smooth_l1_loss(pred[safe,:2],y[safe,:2])
            loss=loss+.2*nn.functional.smooth_l1_loss(pred[:,2],y[:,2])
            optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5)
            optimizer.step()
        val=metrics(model,ts,valid,baseline)
        score=val["endpoint_mae_pixels"]/128+val["risk_brier"]
        history.append({"epoch":epoch+1,**val})
        emit(phase="fit",epoch=epoch+1,endpoint_mae=round(val["endpoint_mae_pixels"],2),risk_brier=round(val["risk_brier"],4))
        if score < best_loss-1e-4:
            best_loss=score;best_weights={k:v.detach().clone() for k,v in model.state_dict().items()};patience=0
        else:
            patience+=1
        if patience>=4:
            break
    if best_weights is None:
        return {"state":"stopped_before_training"}
    model.load_state_dict(best_weights)
    validation=metrics(model,ts,valid,baseline)
    heldout=metrics(model,ts,holdout,baseline)
    qualified=all(m["endpoint_mae_pixels"] < m["constant_endpoint_mae_pixels"]*.9 and
                  m["risk_brier"] < m["constant_risk_brier"] for m in (validation,heldout))
    token_counts=np.bincount(data["plan"][data["split"]==0].reshape(-1),minlength=24)
    report={"state":"trained","samples":meta["samples"],"validation":validation,
            "trained_plan_tokens":[int(i) for i,n in enumerate(token_counts[:PAD]) if n>=20],
            "heldout_maps":heldout,"qualified_for_candidate_ordering":qualified,
            "note":"prediction validation only; not independent navigation/Client clear evidence",
            "history":history}
    payload={"schema":SCHEMA,"physics":meta["physics"],"weights":best_weights,"report":report}
    tmp=output/"latest.tmp";torch.save(payload,tmp);tmp.replace(latest)
    active=output/"active.pt"
    # Compare against the incumbent on the same current validation set before promotion.
    incumbent_score=math.inf
    if active.exists():
        incumbent=torch.load(active,map_location="cpu",weights_only=True)
        if incumbent["schema"]==SCHEMA and incumbent["physics"]==meta["physics"]:
            model.load_state_dict(incumbent["weights"])
            m=metrics(model,ts,valid,baseline)
            incumbent_score=m["endpoint_mae_pixels"]/128+m["risk_brier"]
    promoted=qualified and best_loss<incumbent_score
    if promoted:
        tmp=output/"active.tmp";torch.save(payload,tmp);tmp.replace(active)
    report["promoted"]=promoted
    (output/"model_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 공유 물리 결과 모델", "",f"학습 예제: {meta['samples']}",
           f"검증을 통과한 후보 우선순위 모델 채택: {promoted}","",
           "|평가|위치 오차(px)|상수 예측 오차(px)|복귀 위험 Brier|상수 Brier|",
           "|---|---:|---:|---:|---:|"]
    for name,m in (("보지 않은 상황",validation),("학습에서 제외한 4개 맵",heldout)):
        lines.append(f"|{name}|{m['endpoint_mae_pixels']:.2f}|{m['constant_endpoint_mae_pixels']:.2f}|{m['risk_brier']:.4f}|{m['constant_risk_brier']:.4f}|")
    lines.extend(["","오차/Brier는 낮을수록 좋습니다. 실제 주행 성공률이나 최단 경로 보장이 아닙니다."])
    (output/"MODEL_SUMMARY.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    emit(phase="fit_complete",promoted=promoted,validation=validation,heldout=heldout)
    return report


class CandidateGuide:
    def __init__(self,path):
        torch.set_num_threads(min(2,torch.get_num_threads()))
        saved=torch.load(path,map_location="cpu",weights_only=True)
        from training_archive import physics_fingerprint
        if saved["schema"]!=SCHEMA or saved["physics"]!=physics_fingerprint(ROOT):
            raise ValueError("shared model physics/schema mismatch")
        self.model=OutcomeModel();self.model.load_state_dict(saved["weights"]);self.model.eval()
        self.trained_tokens=set(saved["report"].get("trained_plan_tokens",range(21)))

    def scores(self,context,candidates,budget=64):
        grid,obj,scalar=features(context)
        plans=[plan_tokens(phases,budget) for family,phases in candidates]
        n=len(plans)
        with torch.no_grad():
            p=self.model(torch.from_numpy(np.repeat(grid[None],n,axis=0)),
                         torch.from_numpy(np.repeat(obj[None],n,axis=0)),
                         torch.from_numpy(np.repeat(scalar[None],n,axis=0)),
                         torch.from_numpy(np.stack(plans))).numpy()
        goal=np.asarray(context.get("goal_delta",[0,0]),dtype=np.float32)
        norm=max(float(np.linalg.norm(goal)),1)
        direction=goal/norm
        risk=1/(1+np.exp(-np.clip(p[:,3],-20,20)))
        # A ranking hint, never an admissibility/safety mask. Random trials remain.
        score=np.clip(p[:,:2]@direction,-2,2)-3*risk-.05*np.clip(p[:,2],0,1)
        return [float(value) if all(int(t) in self.trained_tokens for t in plan if t != PAD)
                else None for value,plan in zip(score,plans)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"checkpoints/local_physics_v1")
    p.add_argument("--out",type=Path,default=ROOT/"checkpoints/shared_physics_v1")
    p.add_argument("--epochs",type=int,default=15)
    args=p.parse_args()
    if args.epochs<1:p.error("epochs must be positive")
    fit(args.source,args.out,args.epochs)


if __name__=="__main__":main()
