"""Bounded normal-client trace at input-update entry, with temporary RIGHT shim.
Restores breakpoints/IAT and detaches in finally. Never modifies the executable file.
"""
from capture import *
winmm=C.WinDLL('winmm');winmm.timeGetTime.restype=W.DWORD
class EXCEPTION_RECORD(C.Structure):
    _fields_=[('code',W.DWORD),('flags',W.DWORD),('record',C.c_void_p),('address',C.c_void_p),('count',W.DWORD),('info',C.c_size_t*15)]
class EXCEPTION_INFO(C.Structure):_fields_=[('record',EXCEPTION_RECORD),('first',W.DWORD)]
class EVENT_UNION(C.Union):_fields_=[('exception',EXCEPTION_INFO),('raw',C.c_byte*160)]
class DEBUG_EVENT(C.Structure):_fields_=[('code',W.DWORD),('pid',W.DWORD),('tid',W.DWORD),('u',EVENT_UNION)]
class FLOATING(C.Structure):_fields_=[('words',W.DWORD*7),('registers',C.c_byte*80),('cr0',W.DWORD)]
class WOW_CONTEXT(C.Structure):
    _fields_=[('flags',W.DWORD),('dr',W.DWORD*6),('floating',FLOATING),('segments',W.DWORD*4),('integer',W.DWORD*6),('ebp',W.DWORD),('eip',W.DWORD),('cs',W.DWORD),('eflags',W.DWORD),('esp',W.DWORD),('ss',W.DWORD),('extended',C.c_byte*512)]
for name,args,restype in [
 ('DebugActiveProcess',[W.DWORD],W.BOOL),('DebugActiveProcessStop',[W.DWORD],W.BOOL),('DebugSetProcessKillOnExit',[W.BOOL],W.BOOL),
 ('WaitForDebugEvent',[C.POINTER(DEBUG_EVENT),W.DWORD],W.BOOL),('ContinueDebugEvent',[W.DWORD,W.DWORD,W.DWORD],W.BOOL),
 ('OpenThread',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),('Wow64GetThreadContext',[W.HANDLE,C.POINTER(WOW_CONTEXT)],W.BOOL),('Wow64SetThreadContext',[W.HANDLE,C.POINTER(WOW_CONTEXT)],W.BOOL),
 ('VirtualProtectEx',[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,C.POINTER(W.DWORD)],W.BOOL),
 ('WriteProcessMemory',[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)],W.BOOL),
 ('VirtualAllocEx',[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,W.DWORD],C.c_void_p),
 ('VirtualFreeEx',[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD],W.BOOL),('FlushInstructionCache',[W.HANDLE,C.c_void_p,C.c_size_t],W.BOOL)]:
    f=getattr(k,name);f.argtypes=args;f.restype=restype
def checked(ok):
    if not ok:raise C.WinError(C.get_last_error())
def trace(pid,ticks=12):
    r=Reader(pid);r.close();r.h=k.OpenProcess(0x438,False,pid);checked(r.h)
    bp=0x4228c0+r.delta;iat=0x49c200+r.delta
    original=r.read(bp,1);original_iat=r.read(iat,4)
    if original!=b'\x55':raise RuntimeError('Unexpected input function prologue')
    allocated=0;attached=False;pending=None;stepping=None;states=[];regions=[];meta=None
    def write(a,b):
        old=W.DWORD();checked(k.VirtualProtectEx(r.h,a,len(b),0x40,C.byref(old)))
        try:
            got=C.c_size_t();buf=C.create_string_buffer(b);checked(k.WriteProcessMemory(r.h,a,buf,len(b),C.byref(got)));checked(got.value==len(b));checked(k.FlushInstructionCache(r.h,a,len(b)))
        finally:
            unused=W.DWORD();checked(k.VirtualProtectEx(r.h,a,len(b),old.value,C.byref(unused)))
    def context(tid):
        h=k.OpenThread(0x1a,False,tid);checked(h);c=WOW_CONTEXT();c.flags=0x10001
        checked(k.Wow64GetThreadContext(h,C.byref(c)));return h,c
    try:
        checked(k.DebugActiveProcess(pid));attached=True;checked(k.DebugSetProcessKillOnExit(False))
        write(bp,b'\xcc')
        allocated=k.VirtualAllocEx(r.h,None,4096,0x3000,0x40);checked(allocated)
        # stdcall GetAsyncKeyState: RIGHT high bit, all other keys released.
        write(allocated,bytes.fromhex('837c2404277508b800800000c2040031c0c20400'))
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            e=DEBUG_EVENT()
            if not k.WaitForDebugEvent(C.byref(e),500):continue
            pending=e;status=0x10002
            if e.code==1:
                ex=e.u.exception.record
                if ex.code==0x80000003 and ex.address==bp:
                    h,c=context(e.tid)
                    try:
                        write(bp,original);c.eip=bp;c.eflags&=~0x100
                        states.append(r.state())
                        if len(states)==1:
                            # Snapshot exactly at the first normal input tick boundary.
                            meta={'pid':pid,'state':states[0],'regions':[],'modules':r.modules,'client':r.module,'teb32_candidates':[],'boundary':'4228c0 entry'}
                            a=0;t=time.perf_counter()
                            while a<0x80000000:
                                m=MBI()
                                if not k.VirtualQueryEx(r.h,a,C.byref(m),C.sizeof(m)):break
                                base=m.BaseAddress or 0;size=m.RegionSize
                                if m.State==0x1000 and not(m.Protect&0x101) and m.Type in (0x20000,0x1000000):
                                    data=r.read(base,size);regions.append((base,data));meta['regions'].append({'base':base,'size':size,'protect':m.Protect,'type':m.Type})
                                    for off in range(0,size-0x34,4096):
                                        if struct.unpack_from('<I',data,off+0x18)[0]==base+off:
                                            tls=struct.unpack_from('<I',data,off+0x2c)[0]
                                            if tls:meta['teb32_candidates'].append({'teb':base+off,'tls':tls})
                                a=base+size
                            meta['capture_pause_seconds']=time.perf_counter()-t
                            write(iat,struct.pack('<I',allocated))
                        if len(states)>ticks:
                            checked(k.Wow64SetThreadContext(h,C.byref(c)));break
                        states[-1]['step_time_ms']=winmm.timeGetTime()
                        c.eflags|=0x100;stepping=e.tid;checked(k.Wow64SetThreadContext(h,C.byref(c)))
                    finally:k.CloseHandle(h)
                elif ex.code==0x80000004 and e.tid==stepping:
                    write(bp,b'\xcc');h,c=context(e.tid)
                    try:c.eflags&=~0x100;checked(k.Wow64SetThreadContext(h,C.byref(c)))
                    finally:k.CloseHandle(h)
                    stepping=None
                elif ex.code!=0x80000003:status=0x80010001
            elif e.code==5:raise RuntimeError('Client exited')
            checked(k.ContinueDebugEvent(e.pid,e.tid,status));pending=None
        if len(states)!=ticks+1:raise RuntimeError(f'Timed out: {len(states)} boundaries')
    finally:
        if attached:
            write(bp,original);write(iat,original_iat)
            if pending:checked(k.ContinueDebugEvent(pending.pid,pending.tid,0x10002))
            checked(k.DebugActiveProcessStop(pid))
        # Keep the tiny shim allocation until process exit: another thread might
        # have been executing it when the original IAT was restored.
        r.close()
    out=Path(__file__).parent/'private_snapshots/parity_right12.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for a,b in regions:z.writestr(f'{a:08x}.bin',b)
        z.writestr('metadata.json',json.dumps(meta))
    evidence=Path(__file__).parent/'evidence/normal_right12.json';evidence.write_text(json.dumps({'boundary':'4228c0','keys':['RIGHT'],'states':states,'capture_pause_seconds':meta['capture_pause_seconds']},indent=2))
    print(json.dumps({'ticks':ticks,'start':states[0]['pos'],'end':states[-1]['pos'],'snapshot':str(out),'trace':str(evidence)}))
if __name__=='__main__':trace(int(sys.argv[1]))
