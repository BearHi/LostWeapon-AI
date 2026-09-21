"""Briefly suspend a user-selected Client; capture memory locally; always resume.
No memory writes, network commands, or on-disk Client modifications.
Snapshots can include private session data: never publish the snapshot archive.
"""
from live_state import *
from pathlib import Path
import zipfile,time,hashlib
class MBI(C.Structure):
    _fields_=[('BaseAddress',C.c_void_p),('AllocationBase',C.c_void_p),('AllocationProtect',W.DWORD),('PartitionId',W.WORD),('RegionSize',C.c_size_t),('State',W.DWORD),('Protect',W.DWORD),('Type',W.DWORD)]
k.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t];k.VirtualQueryEx.restype=C.c_size_t
nt=C.WinDLL('ntdll')
nt.NtSuspendProcess.argtypes=[W.HANDLE];nt.NtSuspendProcess.restype=C.c_long
nt.NtResumeProcess.argtypes=[W.HANDLE];nt.NtResumeProcess.restype=C.c_long
def capture(pid,dest):
    r=Reader(pid);r.close();r.h=k.OpenProcess(0xc10,False,pid)
    if not r.h:raise C.WinError(C.get_last_error())
    regions=[];meta={'pid':pid,'regions':[],'modules':r.modules,'client':r.module,'teb32_candidates':[]}
    suspended=False;t=time.perf_counter()
    try:
        if nt.NtSuspendProcess(r.h)<0:raise RuntimeError('Could not suspend Client')
        suspended=True
        meta['state']=r.state()
        if min(meta['state'].get('map_size',[0,0]))<=0:raise RuntimeError('No loaded game map; no capture saved')
        a=0
        while a<0x80000000:
            m=MBI()
            if not k.VirtualQueryEx(r.h,a,C.byref(m),C.sizeof(m)):break
            base=m.BaseAddress or 0;size=m.RegionSize
            if m.State==0x1000 and not (m.Protect&0x101) and (m.Type in (0x20000,0x1000000)):
                data=r.read(base,size);regions.append((base,data))
                meta['regions'].append({'base':base,'size':size,'protect':m.Protect,'type':m.Type})
                for offset in range(0,size-0x34,4096):
                    if struct.unpack_from('<I',data,offset+0x18)[0]==base+offset:
                        tls=struct.unpack_from('<I',data,offset+0x2c)[0]
                        if tls:meta['teb32_candidates'].append({'teb':base+offset,'tls':tls})
            a=base+size
        meta['capture_pause_seconds']=time.perf_counter()-t
    finally:
        if suspended:
            result=nt.NtResumeProcess(r.h)
            if result<0:raise RuntimeError(f'Failed to resume Client: {result}')
        r.close()
    # Compression happens after resuming the game.
    dest=Path(dest);dest.parent.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for base,data in regions:z.writestr(f'{base:08x}.bin',data)
        z.writestr('metadata.json',json.dumps(meta))
    print(json.dumps({'path':str(dest.resolve()),'regions':len(regions),'bytes':sum(len(b) for a,b in regions),'pause_seconds':meta['capture_pause_seconds'],'state':meta['state']},indent=2))
if __name__=='__main__':capture(int(sys.argv[1]),sys.argv[2])
