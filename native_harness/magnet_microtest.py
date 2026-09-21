"""Read-only normal Client raw54 magnet accumulation/release probe."""
from __future__ import annotations
import ctypes as C, json, time, argparse
from pathlib import Path
from normal_trace_readonly import KEYEVENTF_KEYUP, focus_window, process_window, u
from live_state import Reader
VK = {'left': 0x25, 'right': 0x27}
ACC=0x25CA528
DIRECTION=0x25CA078

def sample(reader, phase):
    s=reader.state(); slot=s['slot']
    s['magnet_accumulator']=reader.get(ACC+slot*4,'i')[0]
    s['magnet_direction']=reader.get(DIRECTION+slot*4,'i')[0]
    return {'phase':phase,'perf_ns':time.perf_counter_ns(),'state':s}

def run(pid, output, target_x=288.0, release_seconds=0.9, direction='right'):
    reader=Reader(pid); hwnd=process_window(pid); prior=u.GetForegroundWindow(); pressed=False; rows=[]; last=None
    try:
        focused=False
        for _ in range(8):
            if focus_window(hwnd):
                focused=True
                break
            time.sleep(.08)
        if not focused: raise RuntimeError('Client foreground failed')
        time.sleep(.08); rows.append(sample(reader,'start'))
        key = VK[direction]
        u.keybd_event(key,0,0,0); pressed=True
        deadline=time.perf_counter()+1.5
        while time.perf_counter()<deadline:
            row=sample(reader,'held'); sig=json.dumps(row['state'],sort_keys=True)
            if sig!=last: rows.append(row);last=sig
            x = row['state']['pos'][0]
            if (direction == 'right' and x >= target_x) or (direction == 'left' and x <= target_x): break
        u.keybd_event(key,0,KEYEVENTF_KEYUP,0);pressed=False
        deadline=time.perf_counter()+release_seconds;last=None
        while time.perf_counter()<deadline:
            row=sample(reader,'released');sig=json.dumps(row['state'],sort_keys=True)
            if sig!=last:rows.append(row);last=sig
        result={'scope':f'read-only normal Client horizontal magnet probe with ordinary {direction.upper()} then release','pid':pid,'target_x':target_x,'direction':direction,'samples':rows}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'output':str(output),'samples':len(rows),'start':rows[0]['state']['pos'],'end':rows[-1]['state']['pos'],'max_acc':max(r['state']['magnet_accumulator'] for r in rows),'directions':sorted(set(r['state']['magnet_direction'] for r in rows))},ensure_ascii=False,indent=2))
    finally:
        if pressed:u.keybd_event(VK[direction],0,KEYEVENTF_KEYUP,0)
        if prior and u.GetForegroundWindow()==hwnd:u.SetForegroundWindow(prior)
        reader.close()
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('pid',type=int);ap.add_argument('output',type=Path);ap.add_argument('--target-x',type=float,default=288);ap.add_argument('--release-seconds',type=float,default=.9);ap.add_argument('--direction',choices=('left','right'),default='right');a=ap.parse_args();run(a.pid,a.output,a.target_x,a.release_seconds,a.direction)
