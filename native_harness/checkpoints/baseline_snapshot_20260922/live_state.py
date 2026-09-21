"""Read only the known game-state fields from an explicitly selected Client PID."""
import ctypes as C,struct,json,sys
from ctypes import wintypes as W
k=C.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];k.ReadProcessMemory.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
class MODULEENTRY32W(C.Structure):
    _fields_=[('dwSize',W.DWORD),('th32ModuleID',W.DWORD),('th32ProcessID',W.DWORD),('GlblcntUsage',W.DWORD),('ProccntUsage',W.DWORD),('modBaseAddr',C.c_void_p),('modBaseSize',W.DWORD),('hModule',W.HANDLE),('szModule',W.WCHAR*256),('szExePath',W.WCHAR*260)]
k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)];k.Module32FirstW.restype=W.BOOL
k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)];k.Module32NextW.restype=W.BOOL
def modules(pid):
    h=k.CreateToolhelp32Snapshot(0x18,pid);m=MODULEENTRY32W();m.dwSize=C.sizeof(m);result=[]
    try:
        ok=k.Module32FirstW(h,C.byref(m))
        while ok:
            result.append({'name':m.szModule,'base':m.modBaseAddr,'size':m.modBaseSize,'path':m.szExePath})
            ok=k.Module32NextW(h,C.byref(m))
    finally:k.CloseHandle(h)
    return result
class Reader:
    def __init__(self,pid):
        self.h=k.OpenProcess(0x410,False,pid)
        if not self.h:raise C.WinError(C.get_last_error())
        try:
            self.modules=modules(pid)
            self.module=next(m for m in self.modules if m['name'].lower()=='client.exe')
        except Exception:
            k.CloseHandle(self.h)
            raise
        self.delta=self.module['base']-0x400000
    def read(self,a,n):
        b=C.create_string_buffer(n);got=C.c_size_t()
        if not k.ReadProcessMemory(self.h,a,b,n,C.byref(got)):raise C.WinError(C.get_last_error())
        if got.value!=n:raise RuntimeError('Partial read')
        return b.raw
    def get(self,a,fmt):return struct.unpack('<'+fmt,self.read(a+self.delta,struct.calcsize('<'+fmt)))
    def state(self):
        roster=self.get(0x2248ab4,'i')[0];room=self.get(0xaa16538,'i')[0]
        if not 0<=roster<300:return {'roster':roster,'room':room,'status':'invalid roster'}
        slot=self.get(0x22c31c4+roster*0x130,'b')[0] if room>0 else roster
        if not 0<=slot<300:return {'roster':roster,'room':room,'slot':slot,'status':'invalid slot'}
        p=0x3b12a00+slot*0xf8
        return {'image_base':hex(self.module['base']),'roster':roster,'room':room,'slot':slot,'map_size':self.get(0x8952db0,'ii'),'player_header':self.get(p-16,'4i'),'pos':self.get(p,'dd'),'motion58':self.get(p+0x58,'d')[0],'hp':self.get(p+0x60,'d')[0],'state':{hex(x):self.get(p+x,'i')[0] for x in [0x38,0x3c,0x68,0x74,0xb0,0xc0,0xc4,0xd0,0xdc]},'grid':hex(self.get(0x8952e4c,'I')[0])}
    def close(self):k.CloseHandle(self.h)
if __name__=='__main__':
    r=Reader(int(sys.argv[1]))
    try:print(json.dumps(r.state(),indent=2))
    finally:r.close()
