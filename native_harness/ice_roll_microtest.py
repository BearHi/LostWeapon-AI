"""Read-only normal Client slope momentum probe using an ordinary front roll."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from normal_trace_readonly import KEYEVENTF_KEYUP,focus_window,process_window,u
from live_state import Reader
VK={'left':0x25,'right':0x27,'down':0x28};ACC=0x25CA528;DIRECTION=0x25CA078

def take(reader,phase):
 s=reader.state();slot=s['slot'];s['stored_momentum']=reader.get(ACC+slot*4,'i')[0];s['stored_direction']=reader.get(DIRECTION+slot*4,'i')[0]
 return {'phase':phase,'perf_ns':time.perf_counter_ns(),'state':s}
def run(pid,output,direction='left',hold_ms=335,release_seconds=1.5):
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
  time.sleep(.08);add('start');down(direction);down('down');deadline=time.perf_counter()+hold_ms/1000
  while time.perf_counter()<deadline:add('roll_held')
  up('down');up(direction);deadline=time.perf_counter()+release_seconds
  while time.perf_counter()<deadline:add('released')
  result={'scope':f'read-only normal Client slope momentum probe with ordinary {direction.upper()}+DOWN then release','pid':pid,'direction':direction,'hold_ms':hold_ms,'release_seconds':release_seconds,'samples':rows};output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'output':str(output),'samples':len(rows),'start':rows[0]['state']['pos'],'end':rows[-1]['state']['pos'],'max_momentum':max(r['state']['stored_momentum'] for r in rows),'directions':sorted(set(r['state']['stored_direction'] for r in rows)),'x_range':[min(r['state']['pos'][0] for r in rows),max(r['state']['pos'][0] for r in rows)],'y_range':[min(r['state']['pos'][1] for r in rows),max(r['state']['pos'][1] for r in rows)]},ensure_ascii=False,indent=2))
 finally:
  for k in reversed(pressed):u.keybd_event(VK[k],0,KEYEVENTF_KEYUP,0)
  if prior and u.GetForegroundWindow()==hwnd:u.SetForegroundWindow(prior)
  reader.close()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('pid',type=int);ap.add_argument('output',type=Path);ap.add_argument('--direction',choices=('left','right'),default='left');ap.add_argument('--hold-ms',type=float,default=335);ap.add_argument('--release-seconds',type=float,default=1.5);a=ap.parse_args();run(a.pid,a.output,a.direction,a.hold_ms,a.release_seconds)
