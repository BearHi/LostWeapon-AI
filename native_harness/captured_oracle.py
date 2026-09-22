"""Original relocated x86 code on a captured world. Unknown dependencies fail closed."""
from oracle import *
from headless import KEYS
from unicorn import UC_HOOK_CODE,UC_HOOK_BLOCK,UC_HOOK_MEM_WRITE
import zipfile,json
class CapturedOracle(Oracle):
    CONTROL=0x60000000
    STACK=0x61000000
    GDT=0x62000000
    WORLD_CHAIN=(0x436e30,0x455f00,0x453a50,0x476000,0x461ac0,0x436620,0x415f10)
    CLOCK_MS_PER_TICK=16
    def __init__(self,path):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.fault=None;self.trace=[]
        with zipfile.ZipFile(path) as z:
            self.meta=json.loads(z.read('metadata.json'))
            for r in self.meta['regions']:
                self.u.mem_map(r['base'],r['size'])
                self.u.mem_write(r['base'],z.read(f"{r['base']:08x}.bin"))
        self.base=self.meta['client']['base'];self.delta=self.base-0x400000;self.size=self.meta['client']['size']
        # Different Client sessions place DLL/private regions differently.
        # Pick a free harness block instead of assuming 0x60000000 is unused.
        regions = [(start, end + 1) for start, end, _ in self.u.mem_regions()]
        def reserve(size, candidates):
            address = next((candidate for candidate in candidates
                            if all(candidate + size <= start or candidate >= end
                                   for start, end in regions)), None)
            if address is None:
                raise RuntimeError("no free emulator harness region in captured process")
            regions.append((address, address + size))
            return address
        self.CONTROL = reserve(0x10000, (0x60000000, 0x68000000, 0x70000000,
                                         0x58000000, 0x50000000, 0x48000000))
        self.STACK = reserve(0x100000, (0x61000000, 0x69000000, 0x71000000,
                                       0x59000000, 0x51000000, 0x49000000))
        self.GDT = reserve(0x1000, (0x62000000, 0x6A000000, 0x72000000,
                                   0x5A000000, 0x52000000, 0x4A000000))
        for a,n in [(self.CONTROL,0x10000),(self.STACK,0x100000),(self.GDT,0x1000)]:self.u.mem_map(a,n)
        self.u.reg_write(UC_X86_REG_CR4,0x600);self.u.reg_write(UC_X86_REG_FPCW,0x27f);self.u.reg_write(UC_X86_REG_MXCSR,0x1f80)
        self.u.hook_add(UC_HOOK_MEM_INVALID,self._fault)
        pe=pefile.PE(str(ROOT/'original/Client.exe'))
        self.imports={}
        for j,(dll,imp) in enumerate((d,i) for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports):
            a=self.CONTROL+0x1000+j*16
            name=dll.dll.decode()+':'+(imp.name.decode() if imp.name else str(imp.ordinal))
            keytable=self.CONTROL+0x500
            code=None
            if name.endswith(':GetAsyncKeyState'):
                code=bytes.fromhex('8b54240481e2ff0000000fb70455')+struct.pack('<I',keytable)+bytes.fromhex('66812455')+struct.pack('<I',keytable)+bytes.fromhex('0080c20400')
            elif name.endswith(':timeGetTime'):code=b'\xa1'+struct.pack('<I',self.CONTROL+0x800)+b'\xc3'
            elif name.endswith(':GetLastError'):code=bytes.fromhex('64a134000000c3')
            elif name.endswith(':SetLastError'):code=bytes.fromhex('8b44240464a334000000c20400')
            elif name.endswith(':lstrlenA'):code=bytes.fromhex('8b54240431c0803c0200740340ebf7c20400')
            if code:
                a=self.CONTROL+0x4000+j*64
                self.u.mem_write(a,code)
            self.imports[a]=name
            self.put(imp.address,'I',a)
        self.u.hook_add(UC_HOOK_CODE,self._import,begin=self.CONTROL+0x1000,end=self.CONTROL+0x4000)
        # Actual captured TLS. Candidate self-pointer was validated during capture.
        candidates=self.meta['teb32_candidates']
        if candidates:
            valid=[];index=self.get(0xaa22c8c,'I')[0]
            for candidate in candidates:
                try:
                    peb=struct.unpack('<I',self.u.mem_read(candidate['teb']+0x30,4))[0]
                    if struct.unpack('<I',self.u.mem_read(peb+8,4))[0]!=self.base:continue
                    tls=struct.unpack('<I',self.u.mem_read(candidate['tls']+4*index,4))[0]
                    epoch=struct.unpack('<i',self.u.mem_read(tls+4,4))[0]
                    valid.append((epoch,candidate['teb']))
                except Exception:pass
            # Main game thread has initialized the game's thread-local static guards.
            # This is a captured-state selection heuristic, recorded for validation.
            self.tls_epoch,teb=max(valid);self.teb=teb;limit=0xfffff
            desc=(limit&0xffff)|((teb&0xffff)<<16)|(((teb>>16)&0xff)<<32)|(0x93<<40)|(((limit>>16)&0xf)<<48)|(0xc<<52)|(((teb>>24)&0xff)<<56)
            self.u.mem_write(self.GDT+8,struct.pack('<QQQ',0x00cf9b000000ffff,0x00cf93000000ffff,desc))
            self.u.reg_write(UC_X86_REG_GDTR,(0,self.GDT,0xff,0))
            for reg,sel in [(UC_X86_REG_CS,8),(UC_X86_REG_DS,16),(UC_X86_REG_ES,16),(UC_X86_REG_SS,16),(UC_X86_REG_FS,24)]:self.u.reg_write(reg,sel)
        self.put(self.CONTROL+0x800,'II',self.get(0x24db7f0,'I')[0],0)
        self.put(0x4ae688,'I',0);self.put(0x4ae68c,'I',0)
        # The captured MSVC runtime selected its AVX2 string routines from the
        # host CPU (value 5). Unicorn's x86 backend rejects those AVX opcodes.
        # Select the runtime's equivalent SSE path; return values and gameplay
        # data are unchanged, while goal-completion string handling can run.
        self.put(0xaa22c90,'i',1)
        # Bypass CRT dynamic API resolution, not rand() or physics. Execute the
        # captured Windows FlsGetValue itself so the captured RNG seed is retained.
        fls=self.export('kernelbase.dll','FlsGetValue')
        self.u.hook_add(UC_HOOK_CODE,lambda u,a,s,d:u.reg_write(UC_X86_REG_EIP,fls),begin=self.addr(0x490022),end=self.addr(0x490022))
    def export(self,module,name):
        mod=next(m for m in self.meta['modules'] if m['base']<0x80000000 and m['name'].lower()==module.lower())
        base=mod['base'];p=pefile.PE(data=bytes(self.u.mem_read(base,4096)),fast_load=True)
        rva=p.OPTIONAL_HEADER.DATA_DIRECTORY[0].VirtualAddress
        fields=struct.unpack('<IIHHIIIIIII',self.u.mem_read(base+rva,40))
        _,count,funcs,names,ords=fields[6:]
        for j in range(count):
            ptr=struct.unpack('<I',self.u.mem_read(base+names+j*4,4))[0]
            candidate=bytes(self.u.mem_read(base+ptr,80)).split(b'\0')[0].decode('ascii')
            if candidate==name:
                ordinal=struct.unpack('<H',self.u.mem_read(base+ords+j*2,2))[0]
                return base+struct.unpack('<I',self.u.mem_read(base+funcs+ordinal*4,4))[0]
        raise ValueError(f'Missing export {name}')
    def addr(self,a):return a+self.delta if 0x400000<=a<0xaa36000 else a
    def put(self,a,fmt,*v):self.u.mem_write(self.addr(a),struct.pack('<'+fmt,*v))
    def get(self,a,fmt):return struct.unpack('<'+fmt,self.u.mem_read(self.addr(a),struct.calcsize('<'+fmt)))
    def _import(self,u,a,size,data):
        name=self.imports.get(a)
        if not name:raise RuntimeError(f'Unexpected shim execution {a:x}')
        sp=u.reg_read(UC_X86_REG_ESP)
        ret=struct.unpack('<I',u.mem_read(sp,4))[0];pop=0
        if name.endswith(':GetAsyncKeyState'):
            key=struct.unpack('<I',u.mem_read(sp+4,4))[0]&255
            value=self.get(self.CONTROL+0x500+2*key,'H')[0]
            self.put(self.CONTROL+0x500+2*key,'H',value&0x8000);pop=4
        elif name.endswith(':timeGetTime'):value=self.get(self.CONTROL+0x800,'I')[0]
        elif name.endswith(':GetLastError'):value=struct.unpack('<I',u.mem_read(self.teb+0x34,4))[0]
        elif name.endswith(':SetLastError'):
            value=struct.unpack('<I',u.mem_read(sp+4,4))[0];u.mem_write(self.teb+0x34,struct.pack('<I',value));pop=4
        elif name.endswith(':SetRect'):
            # RECT coordinates are signed LONG values. Reading them as
            # unsigned made legitimate negative off-screen hit boxes overflow
            # when packed back into the captured process.
            rectangle,left,top,right,bottom=struct.unpack('<Iiiii',u.mem_read(sp+4,20))
            u.mem_write(rectangle,struct.pack('<iiii',left,top,right,bottom))
            value=1;pop=20
        elif name.endswith(':GetFocus') or name.endswith(':GetActiveWindow') or name.endswith(':GetForegroundWindow'):
            value=1
        elif name.endswith(':lstrlenA'):
            p=struct.unpack('<I',u.mem_read(sp+4,4))[0];value=0;pop=4
            while u.mem_read(p+value,1)!=b'\0':
                value+=1
                if value>65536:raise RuntimeError('lstrlen input exceeds bound')
        else:raise RuntimeError(f'Unimplemented environment import {name}; caller {ret-self.delta:x}')
        u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_ESP,sp+4+pop);u.reg_write(UC_X86_REG_EIP,ret)
    def call(self,addr,args=b'',limit=2000000):
        sp=self.STACK+0xf0000
        self.u.mem_write(sp,struct.pack('<I',self.CONTROL)+args)
        self.u.reg_write(UC_X86_REG_ESP,sp)
        self.u.emu_start(self.addr(addr),self.CONTROL,count=limit)
        if self.u.reg_read(UC_X86_REG_EIP)!=self.CONTROL:raise RuntimeError('Instruction budget exhausted')
        return self.u.reg_read(UC_X86_REG_EAX)
    def set_input(self,keys):
        unknown=set(keys)-KEYS.keys()
        if unknown:raise ValueError(unknown)
        codes={KEYS[k] for k in keys}
        old=struct.unpack('<256H',self.u.mem_read(self.CONTROL+0x500,512));values=[0]*256
        for key in codes:values[key]=0x8000|(not bool(old[key]&0x8000))
        self.u.mem_write(self.CONTROL+0x500,struct.pack('<256H',*values))
    def step_one_tick(self,keys=(),input_function=0x4228c0,call_limit=2000000):
        self.set_input(keys)
        ms,tick=self.get(self.CONTROL+0x800,'II')
        self.put(self.CONTROL+0x800,'II',ms+self.CLOCK_MS_PER_TICK,tick+1)
        if input_function:self.call(input_function,limit=call_limit)
        self.call(0x436e30,limit=call_limit)
        if (tick+1)%1024==0:self.u.ctl_flush_tb()
        return self.read_player_state()
    def step_world_chain(self,keys=(),call_limit=2000000):
        """Candidate main-loop gameplay chain, excluding render/network presentation."""
        self.set_input(keys)
        ms,tick=self.get(self.CONTROL+0x800,'II')
        self.put(self.CONTROL+0x800,'II',ms+self.CLOCK_MS_PER_TICK,tick+1)
        self.call(0x4228c0,limit=call_limit)
        for address in self.WORLD_CHAIN:self.call(address,limit=call_limit)
        # Unicorn retains translated blocks across emu_start calls. The Client
        # changes enough dispatch paths over a long session for that cache to
        # grow steadily even though game object counts remain constant. A
        # periodic cache flush changes no emulated memory/CPU state.
        if (tick+1)%1024==0:self.u.ctl_flush_tb()
        return self.read_player_state()
    def read_player_state(self):
        # Captured controlled slot is fixed until reset/session identity changes.
        offset=self.meta['state']['slot']*0xf8;p=PLAYER+offset
        return {'x':self.get(p,'d')[0],'y':self.get(p+8,'d')[0],'motion58':self.get(p+0x58,'d')[0],'dash90':self.get(p+0x90,'d')[0],**{f'{x:02x}':self.get(p+x,'i')[0] for x in [0x38,0x3c,0x68,0x74,0x7c,0x80,0xb0,0xb8,0xc0,0xc4,0xd0,0xdc]}}
    def begin_branching(self):
        """One full baseline; restore all pages written by x86 OR host input setup."""
        self.baseline=super().save_snapshot();self.dirty=set()
        original_write=self.u.mem_write
        self._raw_write=original_write
        def mark(addr,size):self.dirty.update(range(addr&~4095,((addr+size-1)&~4095)+1,4096))
        def host_write(addr,data):
            mark(addr,len(data));return original_write(addr,data)
        self.u.mem_write=host_write
        self.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,a,size,value,data:mark(a,size))
    def _baseline_page(self,page):
        """Return one 4 KiB page from the immutable branching baseline."""
        import bisect
        _context, regions = self.baseline
        bases = [a for a, _ in regions]
        index = bisect.bisect_right(bases, page) - 1
        if index < 0:
            raise RuntimeError(f'Baseline page outside mapped regions: {page:#x}')
        address, raw = regions[index]
        if not address <= page < address + len(raw) or page + 4096 > address + len(raw):
            raise RuntimeError(f'Baseline page outside mapped region: {page:#x}')
        return raw[page - address:page - address + 4096]
    def save_branch_snapshot(self):
        """Save CPU state plus only pages changed since ``begin_branching``."""
        pages = {page: bytes(self.u.mem_read(page, 4096)) for page in self.dirty}
        return {
            'kind': 'dirty-branch-v1',
            'context': self.u.context_save(),
            'dirty': tuple(sorted(self.dirty)),
            'pages': pages,
        }
    def restore_branch_snapshot(self, snapshot):
        """Restore a process-local snapshot produced by save_branch_snapshot."""
        if not isinstance(snapshot, dict) or snapshot.get('kind') != 'dirty-branch-v1':
            raise ValueError('snapshot is not a dirty branch snapshot')
        saved_dirty = set(snapshot['dirty'])
        # Clear the current branch first, then apply the saved branch.  This
        # also handles branches whose dirty-page sets differ.
        for page in self.dirty:
            self._raw_write(page, self._baseline_page(page))
        for page, data in snapshot['pages'].items():
            if len(data) != 4096:
                raise ValueError(f'bad branch page length at {page:#x}')
            self._raw_write(page, data)
        self.u.context_restore(snapshot['context'])
        self.dirty = saved_dirty
    def restore_branch(self):
        import bisect
        context,regions=self.baseline;bases=[a for a,b in regions]
        count=len(self.dirty)
        for page in self.dirty:
            i=bisect.bisect_right(bases,page)-1;a,b=regions[i]
            if not a<=page<a+len(b):raise RuntimeError('Written page outside baseline')
            self._raw_write(page,b[page-a:page-a+4096])
        self.u.context_restore(context);self.dirty.clear()
        return count
if __name__=='__main__':
    o=CapturedOracle(sys.argv[1]);print('TEBs',o.meta['teb32_candidates']);print('start',o.read_player_state())
    def trace(u,a,size,data):
        o.trace.append(hex(a-o.delta))
        if len(o.trace)>30:del o.trace[0]
    o.u.hook_add(UC_HOOK_BLOCK,trace)
    try:
        for i in range(12):print(i,o.step_one_tick(['RIGHT']))
    except Exception as e:print('FAIL',str(e),o.fault,'trace',o.trace);raise
