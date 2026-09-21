"""Bounded collection for the next review; never fits or promotes a model."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'checkpoints/week_review_20260919'
DATA = OUT / 'short_native'
DEMO = OUT / 'human'


def trial_count():
    total = 0
    for path in DATA.glob('*.sqlite3'):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
            total += db.execute('select count(*) from trials').fetchone()[0]
    return total


def report():
    lines = ['# 다음 검토용 자료', '', f'갱신: {datetime.now().isoformat(timespec="seconds")}',
             f'짧은 native 실험: {trial_count()}건 (학습/승격 아님)', '',
             '기존 모델: 마지막 15회 승격 0회. 자동 재학습 보류.',
             '사람 입력은 벽시계 표본이며 native tick/정답 라벨이 아닙니다.', '']
    for path in sorted(DEMO.glob('*.jsonl')):
        counts = Counter()
        maps = set()
        first = last = None
        for line in path.open(encoding='utf-8'):
            try:
                row = json.loads(line)
            except ValueError:
                counts['invalid_json'] += 1
                continue
            counts[row.get('event', 'unknown')] += 1
            if row.get('event') == 'human_marker': counts[row['label']] += 1
            if row.get('map'): maps.add(row['map'])
            if row.get('event') == 'sample':
                last = row['wall_time']
                if first is None: first = last
        lines += [f'## {path.name}', f'- events: {dict(counts)}',
                  f'- maps: {sorted(maps)}', f'- sample span seconds: {(last-first) if first else 0:.1f}', '']
    (OUT/'REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
    print(OUT/'REVIEW.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['collect', 'record', 'stop', 'report'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    DEMO.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    if args.mode == 'stop':
        (OUT/'human.STOP').touch()
        (DATA/'STOP').touch()
        return
    if args.mode == 'report':
        report()
        return
    import msvcrt
    with (OUT/(args.mode+'.lock')).open('a+b') as lock:
        if lock.tell() == 0: lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit('Already running. Wait or use the stop launcher.')
        if shutil.disk_usage(OUT).free < 5*1024**3:
            raise SystemExit('Stopped: less than 5 GiB free.')
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        if args.mode == 'record':
            used = sum(p.stat().st_size for p in DEMO.glob('*.jsonl'))
            if used >= 1792*1024**2:
                raise SystemExit('Human recording quota reached; preserve files for review.')
            (OUT/'human.STOP').unlink(missing_ok=True)
            command = [sys.executable, '-u', str(ROOT/'human_play_recorder.py'),
                       '--output', str(DEMO/(stamp+'.jsonl')), '--sample-ms', '20',
                       '--terrain-ms', '100', '--max-minutes', '30', '--max-mb', '256',
                       '--wait-seconds', '120', '--lmf-dir', str(ROOT.parent),
                       '--status-file', str(OUT/'human_status.json'),
                       '--stop-file', str(OUT/'human.STOP')]
            print('Select Client within 120 seconds. F6=good hint F7=mistake F9=pause. 30 min maximum.', flush=True)
        else:
            # Reserve a full 23-map pass. Pending partial targets are at most 32/map.
            if trial_count()+23*32 > 8000:
                raise SystemExit('Short collection quota reached. Preserve data for next review.')
            command = [sys.executable, '-u', str(ROOT/'local_physics_train.py'),
                       '--out', str(DATA), '--resume', '--rounds', '1', '--hours', '1',
                       '--trials-per-map', '32', '--minutes-per-map', '2',
                       '--horizon', '8', '--max-nodes', '4000']
        start = time.time()
        try:
            code = subprocess.run(command, cwd=ROOT, check=False).returncode
        finally:
            report()
        with (OUT/'sessions.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(mode=args.mode, started=start, ended=time.time(),
                                         exit_code=code, command=command), ensure_ascii=False)+'\n')
        raise SystemExit(code)


if __name__ == '__main__':
    main()
