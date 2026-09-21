"""Read-only normal Client jump-across vertical-magnet probe."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from normal_trace_readonly import KEYEVENTF_KEYUP,focus_window,process_window,u
from live_state import Reader
VK={'right':0x27,'up':0x26};PLAYER=0x3B12A00

def take(reader,phase):
 s=reader.state();p=PLAYER+s['slot']*0xf8;s['vertical_magnet_state_d8']=reader.get(p+0xd8,'i')[0]
 return {'phase':phase,'perf_ns':time.perf_counter_ns(),'state':s}
def run(pid,output,jump_hold_ms=35,max_seconds=1.3):
 reader=Reader(pid);hwnd=process_window(pid);prior=u.GetForegroundWindow();pressed=[];rows=[];last=None
 def down(k):u.keybd_event(VK[k],0,0,0);pressed.append(k)
 def up(k):
  if k in pressed:u.keybd_event(VK[k],0,KEYEVENTF_KEYUP,0);pressed.remove(k)
 def add(phase):
  nonlocal last
  r=take(reader,phase);sig=json.dumps(r['state'],sort_keys=True)
  if sig!=last:rows.append(r);last=sig
  return r
 try:
  focused=False
  for _ in range(8):
   if focus_window(hwnd):focused=True;break
   time.sleep(.08)
  if not focused:raise RuntimeError('Client foreground failed')
  time.sleep(.08);start=add('start');down('right');down('up');deadline=time.perf_counter()+jump_hold_ms/1000
  while time.perf_counter()<deadline:add('jump_edge')
  up('up');deadline=time.perf_counter()+max_seconds;crossed=False;reset=None
  while time.perf_counter()<deadline:
   r=add('right_airborne');x,y=r['state']['pos'];crossed=crossed or x>=280
   if crossed and x<=220 and y<=530:reset=r;break
  up('right');end_deadline=time.perf_counter()+.1
  while time.perf_counter()<end_deadline:add('released')
  result={'scope':'read-only normal Client raw52 jump-crossing probe with ordinary RIGHT+UP then RIGHT','pid':pid,'jump_hold_ms':jump_hold_ms,'reset_detected':reset is not None,'samples':rows};output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'output':str(output),'samples':len(rows),'reset_detected':reset is not None,'d8_values':sorted(set(r['state']['vertical_magnet_state_d8'] for r in rows)),'motion_range':[min(r['state']['motion58'] for r in rows),max(r['state']['motion58'] for r in rows)],'x_range':[min(r['state']['pos'][0] for r in rows),max(r['state']['pos'][0] for r in rows)],'y_range':[min(r['state']['pos'][1] for r in rows),max(r['state']['pos'][1] for r in rows)]},ensure_ascii=False,indent=2))
 finally:
  for k in reversed(pressed):u.keybd_event(VK[k],0,KEYEVENTF_KEYUP,0)
  if prior and u.GetForegroundWindow()==hwnd:u.SetForegroundWindow(prior)
  reader.close()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('pid',type=int);ap.add_argument('output',type=Path);ap.add_argument('--jump-hold-ms',type=float,default=35);ap.add_argument('--max-seconds',type=float,default=1.3);a=ap.parse_args();run(a.pid,a.output,a.jump_hold_ms,a.max_seconds)
