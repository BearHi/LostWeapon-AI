"""Read-only normal Client vertical-magnet positioning and jump probe."""
from __future__ import annotations
import argparse, ctypes as C, json, time
from pathlib import Path
from normal_trace_readonly import KEYEVENTF_KEYUP, focus_window, process_window, u
from live_state import Reader
VK={'left':0x25,'up':0x26,'right':0x27}
PLAYER=0x3B12A00

def sample(reader,phase):
 s=reader.state();p=PLAYER+s['slot']*0xf8;s['vertical_magnet_state_d8']=reader.get(p+0xd8,'i')[0]
 return {'phase':phase,'perf_ns':time.perf_counter_ns(),'state':s}

def run(pid,output,target_x,direction='right',settle_ms=35,jump_hold_ms=35,duration=2.2):
 reader=Reader(pid);hwnd=process_window(pid);prior=u.GetForegroundWindow();pressed=[];rows=[];last=None
 def down(name):u.keybd_event(VK[name],0,0,0);pressed.append(name)
 def up(name):
  if name in pressed:u.keybd_event(VK[name],0,KEYEVENTF_KEYUP,0);pressed.remove(name)
 def add(phase):
  nonlocal last
  row=sample(reader,phase);sig=json.dumps(row['state'],sort_keys=True)
  if sig!=last:rows.append(row);last=sig
  return row
 try:
  focused=False
  for _ in range(8):
   if focus_window(hwnd):focused=True;break
   time.sleep(.08)
  if not focused:raise RuntimeError('Client foreground failed')
  time.sleep(.08);add('start');down(direction);deadline=time.perf_counter()+1.5
  while time.perf_counter()<deadline:
   row=add('positioning');x=row['state']['pos'][0]
   if (direction=='right' and x>=target_x) or (direction=='left' and x<=target_x):break
  up(direction);deadline=time.perf_counter()+settle_ms/1000
  while time.perf_counter()<deadline:add('settle')
  down('up');deadline=time.perf_counter()+jump_hold_ms/1000
  while time.perf_counter()<deadline:add('jump_edge')
  up('up');deadline=time.perf_counter()+duration
  while time.perf_counter()<deadline:add('airborne')
  result={'scope':'read-only normal Client vertical magnet probe with ordinary positioning and UP','pid':pid,'target_x':target_x,'direction':direction,'settle_ms':settle_ms,'jump_hold_ms':jump_hold_ms,'duration':duration,'samples':rows}
  output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'output':str(output),'samples':len(rows),'start':rows[0]['state']['pos'],'end':rows[-1]['state']['pos'],'d8_values':sorted(set(r['state']['vertical_magnet_state_d8'] for r in rows)),'motion_range':[min(r['state']['motion58'] for r in rows),max(r['state']['motion58'] for r in rows)],'y_range':[min(r['state']['pos'][1] for r in rows),max(r['state']['pos'][1] for r in rows)]},ensure_ascii=False,indent=2))
 finally:
  for name in reversed(pressed):u.keybd_event(VK[name],0,KEYEVENTF_KEYUP,0)
  if prior and u.GetForegroundWindow()==hwnd:u.SetForegroundWindow(prior)
  reader.close()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('pid',type=int);ap.add_argument('output',type=Path);ap.add_argument('--target-x',type=float,required=True);ap.add_argument('--direction',choices=('left','right'),default='right');ap.add_argument('--settle-ms',type=float,default=35);ap.add_argument('--jump-hold-ms',type=float,default=35);ap.add_argument('--duration',type=float,default=2.2);a=ap.parse_args();run(a.pid,a.output,a.target_x,a.direction,a.settle_ms,a.jump_hold_ms,a.duration)
