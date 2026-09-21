from oracle import *
from unicorn import UC_HOOK_CODE
import json
o=Oracle();o.fixture();u=o.u
# Minimal synthetic one-player world; explicitly not a valid captured game session.
o.put(0x2248ab4,'I',0);o.put(0x22c30c4,'i',1)
o.put(0x25a2518,'I',1);o.put(0x25a2068,'I',0)
o.put(PLAYER+0x60,'d',100.);o.put(PLAYER+0x78,'i',1)
o.put(0x25ca078,'i',-1)
o.put(0x4ae688,'I',0);o.put(0x4ae68c,'I',0)
for x in range(32):o.tile(x,11,1)
o.put(0x49c200,'I',0x30000100)
o.put(0x49c2bc,'I',0x30000110)
o.put(0x49c070,'I',0x30000120)
u.mem_write(0x30000100,b'\x31\xc0\xc2\x04\x00')
u.mem_write(0x30000110,b'\xb8\x00\x00\x00\x00\xc3')
# lstrlenA, stdcall: count bytes until NUL.
u.mem_write(0x30000120,bytes.fromhex('8b54240431c0803c0200740340ebf7c20400'))
trace=[]
def block(u,a,size,data):
    trace.append(hex(a))
    if len(trace)>80:del trace[0]
from unicorn import UC_HOOK_BLOCK
u.hook_add(UC_HOOK_BLOCK,block)
try:
    for i in range(3):
        o.call(0x436e30)
        print(i,o.read_player_state())
except Exception as e:print('FAIL',str(e),o.fault,'last_blocks',trace)
