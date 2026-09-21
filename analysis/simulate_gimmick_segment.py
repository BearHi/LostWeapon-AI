"""Query an empirical trajectory inside its measured time interval only.

This is a vertical free-flight prediction probe, not a full game simulator.
Refuse segments whose temporal holdout max error exceeds 0.25 cells.
"""
import argparse,json
from pathlib import Path
from fit_gimmick_motion import predict


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trial',required=True)
    ap.add_argument('--phase',choices=['pre','post'],default='pre')
    ap.add_argument('--time',type=float,required=True,help='absolute source-video seconds')
    args=ap.parse_args()
    path=Path(__file__).parent/'motion_180606'/'refined'/'segment_models.json'
    all_models=json.loads(path.read_text(encoding='utf-8'))
    m=all_models[args.trial][args.phase+'_roll_fit']
    if m.get('test_max_error_cells',float('inf'))>.25:
        raise SystemExit('REJECTED: insufficient samples or held-out error above 0.25 cells; do not use this prediction.')
    start=min(m['train_frames'])/60;end=max(m['test_frames'])/60
    if not start<=args.time<=end:raise SystemExit('REJECTED: requested time is outside measured segment.')
    print(json.dumps({'trial':args.trial,'source_time_s':args.time,
                      'predicted_y_cells':predict(m,args.time),
                      'measured_holdout_max_error_cells':m['test_max_error_cells'],
                      'status':'local_video_fit_only_not_route_certification'},indent=2))


if __name__=='__main__':main()
