from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
p=pefile.PE(str(ROOT/'original/Client.exe'))
base=p.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_32)
md.skipdata=True
ins=[]
for s in p.sections:
    if s.Characteristics & 0x20000000:
        ins.extend(md.disasm(s.get_data(),base+s.VirtualAddress))
imports={i.address:(d.dll.decode()+':'+(i.name.decode() if i.name else str(i.ordinal))) for d in p.DIRECTORY_ENTRY_IMPORT for i in d.imports}
out=ROOT/'evidence';out.mkdir(exist_ok=True)
(out/'disassembly.txt').write_text('\n'.join(f'{i.address:08x}: {i.mnemonic} {i.op_str}' for i in ins))
meta={'sha256':hashlib.sha256((ROOT/'original/Client.exe').read_bytes()).hexdigest(),'machine':hex(p.FILE_HEADER.Machine),'base':hex(base),'entry':hex(base+p.OPTIONAL_HEADER.AddressOfEntryPoint),'size':hex(p.OPTIONAL_HEADER.SizeOfImage),'sections':[{'name':s.Name.decode().strip('\0'),'va':hex(base+s.VirtualAddress),'vsize':hex(s.Misc_VirtualSize),'raw':s.SizeOfRawData} for s in p.sections],'imports':{hex(k):v for k,v in imports.items()}}
(out/'pe.json').write_text(json.dumps(meta,indent=2))
print(json.dumps({k:v for k,v in meta.items() if k!='imports'},indent=2))
targets=[0x459be0,0x41aba0,0x41ac80,0x41ac30]
for t in targets:
    print('\nTARGET',hex(t),'CALLERS',[hex(i.address) for i in ins if i.mnemonic=='call' and i.op_str==hex(t)])
    print('\n'.join(f'{i.address:08x}: {i.mnemonic} {i.op_str}' for i in md.disasm(p.get_data(t-base,160),t)))
print('TIMING/INPUT IMPORTS',{hex(k):v for k,v in imports.items() if any(x.lower() in v.lower() for x in ['sleep','time','key','direct','recv','send'])})
