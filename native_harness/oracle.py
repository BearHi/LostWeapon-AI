"""Execute unchanged Client x86. Fixtures are synthetic, not captured game states."""
from pathlib import Path
import sys,struct,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_MEM_INVALID
from unicorn.x86_const import *
EXPECTED='051119bcbd521ce18d1e8636e749dc05eee1958b4cf50d2c13a816ba5898df15'
PLAYER=0x3b12a00
class Oracle:
    def __init__(self):
        raw=(ROOT/'original/Client.exe').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=EXPECTED: raise ValueError('Wrong Client version')
        pe=pefile.PE(data=raw)
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.base=pe.OPTIONAL_HEADER.ImageBase
        self.size=pe.OPTIONAL_HEADER.SizeOfImage
        self.u.mem_map(self.base,self.size)
        self.u.mem_write(self.base,raw[:pe.OPTIONAL_HEADER.SizeOfHeaders])
        for s in pe.sections:self.u.mem_write(self.base+s.VirtualAddress,s.get_data())
        self.u.mem_map(0x10000000,0x200000) # fixture grids
        self.u.mem_map(0x20000000,0x100000) # stack
        self.u.mem_map(0x30000000,0x1000) # return sentinel / batch code
        self.u.reg_write(UC_X86_REG_CR4,0x600)
        self.u.reg_write(UC_X86_REG_FPCW,0x37f)
        self.u.reg_write(UC_X86_REG_MXCSR,0x1f80)
        self.fault=None
        self.u.hook_add(UC_HOOK_MEM_INVALID,self._fault)
    def _fault(self,u,access,address,size,value,data):
        self.fault={'eip':hex(u.reg_read(UC_X86_REG_EIP)),'address':hex(address),'access':access,'size':size}
        return False
    def put(self,a,fmt,*v):self.u.mem_write(a,struct.pack('<'+fmt,*v))
    def get(self,a,fmt):return struct.unpack('<'+fmt,self.u.mem_read(a,struct.calcsize('<'+fmt)))
    def call(self,addr,args=b'',limit=1000000):
        sp=0x200f0000
        self.u.mem_write(sp,struct.pack('<I',0x30000000)+args)
        self.u.reg_write(UC_X86_REG_ESP,sp)
        self.u.emu_start(addr,0x30000000,count=limit)
        if self.u.reg_read(UC_X86_REG_EIP)!=0x30000000:raise RuntimeError('Instruction budget exhausted')
        return self.u.reg_read(UC_X86_REG_EAX)
    def fixture(self,w=32,h=24):
        self.w,self.h=w,h
        self.put(0x8952db0,'II',w,h)
        self.put(0xa073150,'I'*h,*[y*w for y in range(h)])
        for a in [0x8952dec,0x8952e2c,0x8952e4c,0x8952dcc]:self.put(a,'I',0x10000000)
        self.put(0xaa16538,'I',0)
        self.put(0xaa04116,'B',0)
        self.u.mem_write(0x10000000,bytes(w*h*2))
        self.u.mem_write(PLAYER,bytes(0xf8))
        self.put(PLAYER,'dd',160.,320.)
        self.put(PLAYER+0xd0,'i',1)
    def tile(self,x,y,code):self.put(0x10000000+2*(y*self.w+x),'H',code)
    def collision(self,x,y,hard=False):return self.call(0x41ac30 if hard else 0x41ac80,struct.pack('<ii',x,y))
    def move(self,direction,distance):return self.call(0x459be0,struct.pack('<iid',0,direction,distance))
    def read_player_state(self):
        return {'x':self.get(PLAYER,'d')[0],'y':self.get(PLAYER+8,'d')[0],'motion58':self.get(PLAYER+0x58,'d')[0],**{f'{x:02x}':self.get(PLAYER+x,'i')[0] for x in [0x38,0x3c,0x68,0x74,0x7c,0x80,0xb0,0xb8,0xc0,0xc4,0xd0,0xdc]}}
    def save_snapshot(self):
        # Full mapped emulator memory and CPU; intentionally no guessed player-only snapshot.
        return (self.u.context_save(),[(a,bytes(self.u.mem_read(a,b-a+1))) for a,b,p in self.u.mem_regions()])
    def restore_snapshot(self,snapshot):
        context,regions=snapshot
        for a,b in regions:self.u.mem_write(a,b)
        self.u.context_restore(context)
