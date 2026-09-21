"""Experimental native dispatcher with synthetic world initialization.
Not a parity-certified game tick or complete RL environment.
"""
from oracle import *
import zipfile
KEYS={'LEFT':0x25,'UP':0x26,'RIGHT':0x27,'DOWN':0x28,'SPACE':0x20,
      'Z':0x5a,'X':0x58,'C':0x43,**{str(i):0x30+i for i in range(1,9)}}
class Headless(Oracle):
    def __init__(self):
        super().__init__()
        # Environment shims only. No original physics instruction is patched.
        self.put(0x49c200,'I',0x30000100)
        self.put(0x49c2bc,'I',0x30000120)
        self.put(0x49c070,'I',0x30000130)
        # GetAsyncKeyState: keyed 16-bit return table, preserving simultaneous inputs.
        self.u.mem_write(0x30000100,bytes.fromhex('8b44240425ff0000000fb7044500080030c20400'))
        self.u.mem_write(0x30000120,bytes.fromhex('a100070030c3'))
        self.u.mem_write(0x30000130,bytes.fromhex('8b54240431c0803c0200740340ebf7c20400'))
        self.fixture()
        self.put(0x2248ab4,'I',0);self.put(0x22c30c4,'i',1)
        self.put(0x25a2518,'I',1);self.put(0x25a2068,'I',0)
        self.put(PLAYER+0x60,'d',100.);self.put(PLAYER+0x78,'i',1)
        self.put(0x25ca078,'i',-1)
        self.put(0x4ae688,'I',0);self.put(0x4ae68c,'I',0)
        for x in range(self.w):self.tile(x,11,1)
        self.load_body_metadata()
    def load_body_metadata(self):
        # Layout independently traced to original loaders 46c7b0 and 46b700.
        # Fixture binds body to resource 0; actual session resource choice is uncaptured.
        with zipfile.ZipFile(r'C:\Users\microsoft\Downloads\NewLostweapon\NewLostweapon3.zip') as z:
            ani=z.read('Data/body.ani');spr=z.read('Data/body.spr')
        n=struct.unpack_from('<I',ani)[0];end=12+12*n
        count=struct.unpack_from('<I',ani,end)[0]
        assert len(ani)==end+4+8*count
        self.u.mem_write(0x70e8db0,ani[12:end])
        self.u.mem_write(0x87cc3b0,ani[end+4:])
        self.put(0xa074140,'I',count);self.put(0xa072dd0,'I',n)
        mode=struct.unpack_from('<I',spr)[0];assert mode in (0,1,2)
        frames=struct.unpack_from('<I',spr,18)[0]
        self.put(0x3b3adbc,'I',frames)
        self.u.mem_write(0x3b3adc0,spr[22:22+16*frames])
        self.u.mem_write(0x3b61ec0,spr[22+16*frames:22+20*frames])
        self.u.mem_write(0x3b6bb00,spr[22+20*frames:22+24*frames])
        self.put(0xa072aa8,'I',1)
    def set_input(self,keys):
        unknown=set(keys)-KEYS.keys()
        if unknown:raise ValueError(f'Not gameplay keys: {unknown}')
        self.u.mem_write(0x30000800,bytes(512))
        for key in keys:self.put(0x30000800+KEYS[key]*2,'H',0x8000)
    def step_dispatch(self):
        # Logical clock only; 60Hz is a hypothesis until normal-client tick comparison.
        tick=self.get(0x30000704,'I')[0]+1
        self.put(0x30000700,'II',tick*1000//60,tick)
        self.call(0x436e30)
        return self.read_player_state()
