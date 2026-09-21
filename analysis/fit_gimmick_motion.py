"""Fit empirical free-flight segments and test on later held-out samples.

This does not predict how surfaces create velocity, nor certify LMF routes.
"""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'video_runtime'))
import numpy as np
from verified_gimmick_samples import verified

ROOT=Path(__file__).parent/'motion_180606'
OUT=ROOT/'refined'
TRIALS={
 'M1':(102,136,48),'M2':(450,481,48),'M3':(813,859,48),'M4':(1129,1169,48),
 'I1':(1915,1956,48),'I2':(2462,2520,None),'I3':(2872,2926,None),'I4':(3049,3088,48)}
VISUAL_FREE_FLIGHT_END={'I2':2574,'I3':2997}


def parse(raw,axis):
    m=re.fullmatch(r'(\d{1,2}):\s*(\d{1,2}\.\d{3})',raw.strip().replace(',','.'))
    if not m:return None
    cell,offset=int(m[1]),float(m[2])
    if not 0<=offset<32:return None
    value=cell+offset/32
    return value if 0<=value<=(72 if axis=='x' else 56) else None


def predict(model,t):
    """y in cells, positive down, t in source-video seconds."""
    dt=t-model['reference_time_s']
    a,b,c=model['coefficients_a_b_c']
    return a*dt*dt+b*dt+c


def fit(points):
    if len(points)<10:return {'status':'insufficient_samples','samples':len(points)}
    t0=points[0]['time_s']
    split=max(7,int(len(points)*.7))
    train_raw,test=points[:split],points[split:]
    if len(test)<3:return {'status':'insufficient_holdout','samples':len(points)}
    ts=np.array([p['time_s']-t0 for p in train_raw]);ys=np.array([p['y'] for p in train_raw])
    # Screen TRAINING OCR outliers only. All later held-out observations stay
    # in the error calculation, so prediction failure cannot be hidden here.
    keep=np.ones(len(train_raw),dtype=bool)
    for _ in range(3):
        if keep.sum()<6:break
        coeff=np.polyfit(ts[keep],ys[keep],2)
        residual=np.abs(np.polyval(coeff,ts)-ys)
        scale=max(.15,float(np.median(residual[keep]))*4)
        proposed=residual<scale
        if proposed.sum()<6:break
        keep=proposed
    train=[p for p,k in zip(train_raw,keep) if k]
    train_t=np.array([p['time_s']-t0 for p in train]);train_y=np.array([p['y'] for p in train])
    a,b,c=np.polyfit(train_t,train_y,2)
    model={'status':'video_fit_not_game_engine','reference_time_s':t0,
           'coefficients_a_b_c':[float(a),float(b),float(c)],
           'effective_acceleration_cells_s2':float(2*a),
           'vertical_velocity_at_reference_cells_s':float(b),
           'train_frames':[p['frame'] for p in train],
           'test_frames':[p['frame'] for p in test],
           'excluded_training_frames':[p['frame'] for p,k in zip(train_raw,keep) if not k],
           'holdout_note':'Train-only OCR outlier screening; all later test samples retained. Not an independent trial validation.'}
    errors=[predict(model,p['time_s'])-p['y'] for p in test]
    model.update(test_rmse_cells=float(np.sqrt(np.mean(np.square(errors)))),
                 test_max_error_cells=float(max(map(abs,errors))),
                 test_predictions=[{'frame':p['frame'],'observed_y':p['y'],
                                    'predicted_y':predict(model,p['time_s'])} for p in test])
    model['local_prediction_check']='within_0.25_cells' if model['test_max_error_cells']<=.25 else 'rejected_over_0.25_cells'
    model['valid_source_time_interval_s']=[min(model['train_frames'])/60,max(model['test_frames'])/60]
    return model


def main():
    rows=json.loads((OUT/'coordinates.json').read_text(encoding='utf-8'))
    manual=verified()
    grouped={t:[] for t in TRIALS}
    for row in rows:
        p={k:row[k] for k in ('trial','frame','time_s')}
        for line in row['lines']:
            p['raw_'+line['axis']]=line['raw']
            p[line['axis']]=parse(line['raw'],line['axis']) if line['confidence']>=.85 else None
        if row['frame'] in manual:
            v=manual[row['frame']]
            assert v['trial']==row['trial']
            p.update(y=v['y'],raw_y=v['raw_y'],verification='visual_source_read',source=v['source'])
        grouped[p['trial']].append(p)
    report={}
    for name,pts in grouped.items():
        jump,roll,launch_y=TRIALS[name]
        usable=[p for p in pts if p.get('y') is not None]
        before=[p for p in usable if jump+8<=p['frame']<=roll-3]
        after=[p for p in usable if p['frame']>=roll+12 and p['y']<47.8]
        if name in VISUAL_FREE_FLIGHT_END:
            after=[p for p in after if p['frame']<=VISUAL_FREE_FLIGHT_END[name]]
        # Remove known slope contact; post-roll contact may otherwise bias g.
        after=[p for p in after if not (p.get('x') is not None and 48<=p['x']<=56 and abs(p['y']-(p['x']-8))<.1)]
        # Only the uninterrupted flight before the first subsequent landing.
        if after:
            end=next((p['frame'] for p in usable if p['frame']>after[0]['frame'] and
                      (abs(p['y']-48)<.01 or (p.get('x') is not None and 48<=p['x']<=56 and abs(p['y']-(p['x']-8))<.1))),None)
            if end is not None:after=[p for p in after if p['frame']<end]
        pre_peak=min(before,key=lambda p:p['y']) if before else None
        post_peak=min(after,key=lambda p:p['y']) if after else None
        report[name]={'jump_input_frame':jump,'roll_down_frame':roll,'known_launch_y':launch_y,
                      'pre_roll_peak_sample':pre_peak,'post_roll_peak_sample':post_peak,
                      'pre_roll_fit':fit(before),'post_roll_fit':fit(after),
                      'coordinate_samples':pts}
    (OUT/'segment_models.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'verified_y.json').write_text(json.dumps(manual,ensure_ascii=False,indent=2),encoding='utf-8')
    # Independent-trial transfer: learn one acceleration on M3; estimate only
    # initial position/velocity on the first half of each OTHER jump, then
    # predict the second half. No roll or contact samples cross the boundary.
    base=report['M3']
    baseline=[p for p in base['coordinate_samples'] if p.get('y') is not None and 821<=p['frame']<=856]
    bt=np.array([p['time_s']-baseline[0]['time_s'] for p in baseline])
    by=np.array([p['y'] for p in baseline])
    accel=float(2*np.polyfit(bt,by,2)[0])
    transfer={'acceleration_learned_from_M3_only':accel,'source_frames':[p['frame'] for p in baseline],'trials':{}}
    for name in ('I1','I2','I3','I4'):
        jump,roll,_=TRIALS[name]
        points=[p for p in report[name]['coordinate_samples'] if p.get('y') is not None and jump+8<=p['frame']<=roll-3]
        cut=max(4,len(points)//2);train,test=points[:cut],points[cut:]
        t0=points[0]['time_s'];tt=np.array([p['time_s']-t0 for p in train]);yy=np.array([p['y'] for p in train])
        v,c=np.polyfit(tt,yy-.5*accel*tt*tt,1)
        predictions=[{'frame':p['frame'],'observed_y':p['y'],
                      'predicted_y':float(c+v*(p['time_s']-t0)+.5*accel*(p['time_s']-t0)**2)} for p in test]
        errors=[p['predicted_y']-p['observed_y'] for p in predictions]
        transfer['trials'][name]={'reference_time_s':t0,'velocity_at_reference':float(v),
                                'position_at_reference':float(c),'train_frames':[p['frame'] for p in train],
                                'test':predictions,'rmse_cells':float(np.sqrt(np.mean(np.square(errors)))),
                                'max_error_cells':float(max(map(abs,errors)))}
    (OUT/'shared_acceleration_test.json').write_text(json.dumps(transfer,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TRANSFER',accel,[(k,round(v['rmse_cells'],3),round(v['max_error_cells'],3)) for k,v in transfer['trials'].items()])
    for name,r in report.items():
        print(name, 'pre/post sampled Y',*[round(r[k]['y'],4) if r[k] else None for k in ('pre_roll_peak_sample','post_roll_peak_sample')])
        for key in ('pre_roll_fit','post_roll_fit'):
            m=r[key]
            print(key, {k:round(m[k],4) for k in ('effective_acceleration_cells_s2','vertical_velocity_at_reference_cells_s','test_rmse_cells','test_max_error_cells') if k in m},m['status'])


if __name__=='__main__':main()
