"""Read-only PE and known-cleared LMF inspection. Never launch/modify clients.

Only gameplay-related string/symbol matches are reported; login/config files
and network behavior are out of scope.
"""
import hashlib,json,re,struct,math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis'/'system_model';OUT.mkdir(exist_ok=True)
PHYS=re.compile(r'gravity|collis|collid|magnet|jump|parach|spring|block|ground|player|character|move|rotate|fall|wind|ice',re.I)


def pe(path):
    b=path.read_bytes();p=struct.unpack_from('<I',b,0x3c)[0]
    assert b[p:p+4]==b'PE\0\0'
    machine,nsec,stamp,symptr,nsyms,optlen,flags=struct.unpack_from('<HHIIIHH',b,p+4)
    imagebase=struct.unpack_from('<I',b,p+24+28)[0]
    sections=[]
    for i in range(nsec):
        off=p+24+optlen+40*i
        name=b[off:off+8].split(b'\0')[0].decode('ascii','replace')
        vsize,rva,size,raw=struct.unpack_from('<IIII',b,off+8)
        data=b[raw:raw+size];c=Counter(data)
        entropy=-sum((n/len(data))*math.log2(n/len(data)) for n in c.values()) if data else 0
        sections.append({'name':name,'rva':rva,'virtual_size':vsize,'raw_offset':raw,'raw_size':size,'entropy':round(entropy,3)})
    symbols=[]
    stringsbase=symptr+nsyms*18
    if symptr and stringsbase+4<=len(b):
        i=0
        while i<nsyms:
            off=symptr+18*i
            if off+18>len(b):break
            a=b[off:off+8]
            if a[:4]==b'\0'*4:
                pos=stringsbase+struct.unpack_from('<I',a,4)[0]
                name=b[pos:pos+500].split(b'\0')[0].decode('ascii','replace')
            else:name=a.split(b'\0')[0].decode('ascii','replace')
            value,section,typ,storage,aux=struct.unpack_from('<IhHBB',b,off+8)
            if PHYS.search(name):symbols.append({'name':name,'value':value,'section':section,'type':typ,'storage':storage})
            i+=1+aux
    strings=[]
    for m in re.finditer(rb'[ -~]{5,160}',b):
        s=m[0].decode('ascii')
        if PHYS.search(s) and re.search(r'[A-Za-z]{4}',s):
            strings.append({'file_offset':m.start(),'text':s})
    return {'path':str(path),'sha256':hashlib.sha256(b).hexdigest(),'size':len(b),
            'machine':hex(machine),'image_base':imagebase,'sections':sections,
            'coff_symbol_count':nsyms,'physics_symbol_matches':symbols,
            'gameplay_string_matches':strings[:150]}


def lmf(path,clear_status):
    b=path.read_bytes();w,h=struct.unpack_from('<HH',b,16);n=struct.unpack_from('<I',b,21)[0]
    assert len(b)>=32+n*8
    records=[struct.unpack_from('<Ihh',b,32+8*i) for i in range(n)]
    positions=Counter((x,y) for _,x,y in records)
    return {'path':str(path),'sha256':hashlib.sha256(b).hexdigest(),'size':len(b),
            'width':w,'height':h,'records':n,'trailing_bytes':len(b)-32-8*n,
            'tile_counts_decimal':dict(sorted(Counter(t for t,_,_ in records).items())),
            'overlapping_positions':sum(v>1 for v in positions.values()),
            'spawns':[[x,y] for t,x,y in records if t==100],
            'out_of_bounds_records':[[t,x,y] for t,x,y in records if not 0<=x<w or not 0<=y<h],
            'clear_status':clear_status,'engine_model_verifies_clear':False}


def main():
    files=[ROOT/'로스트웨폰 클라이언트'/'Client.exe',Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Client.exe'),ROOT/'LMFeditor.exe']
    report={'executables':[pe(p) for p in files if p.exists()],
            'references':[lmf(Path(r'C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF'),'user_confirmed_cleared'),
                          lmf(ROOT/'암벽_신설안_v8_암반윤곽형.LMF','user_reported_all_clear_in_thread'),
                          lmf(ROOT/'학습용'/'암벽11.LMF','reference_for_gimmicks_not_model_verified')]}
    (OUT/'engine_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in report['executables']:
        print(Path(r['path']).name,r['size'],r['sha256'], 'COFF',r['coff_symbol_count'])
        print('sections',[(s['name'],s['raw_size'],s['entropy']) for s in r['sections']])
        print('physics_symbols',r['physics_symbol_matches'][:30])
        print('strings',r['gameplay_string_matches'][:25])
    print('REFERENCES',json.dumps(report['references'],ensure_ascii=True))


if __name__=='__main__':main()
