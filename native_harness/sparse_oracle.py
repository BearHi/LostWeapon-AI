"""Sparse mapped variant of the captured oracle.

Only pages observed by the offline closure footprint are mapped. It is a
validation tool for state-subset reduction, not yet a general map loader.
"""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle

class SparseCapturedOracle(CapturedOracle):
    def __init__(self,snapshot,footprint=None):
        super().__init__(snapshot)
        footprint=Path(footprint or ROOT/'evidence/subset_analysis.json')
        fd=json.loads(footprint.read_text())
        pages=set()
        for item in fd['scenarios'].values():
            pages.update(int(x,16) for x in item.get('read_ranges',[]))
            pages.update(int(x,16) for x in item.get('write_ranges',[]))
            pages.update(int(x,16) for x in item.get('exec_ranges',[]))
        pages={p for p in pages if not (self.CONTROL<=p<self.CONTROL+0x10000 or self.STACK<=p<self.STACK+0x100000 or self.GDT<=p<self.GDT+0x1000)}
        original=[(a,b,p) for a,b,p in self.u.mem_regions() if not (self.CONTROL<=a<self.CONTROL+0x10000 or self.STACK<=a<self.STACK+0x100000 or self.GDT<=a<self.GDT+0x1000)]
        bytes_by_page={}
        for page in pages:
            for a,b,p in original:
                if a<=page<=b:
                    bytes_by_page[page]=bytes(self.u.mem_read(page,0x1000));break
        for a,b,p in original:self.u.mem_unmap(a,b-a+1)
        for page,data in bytes_by_page.items():
            self.u.mem_map(page,0x1000,7);self.u.mem_write(page,data)
        self.sparse_pages=sorted(bytes_by_page)
        self.footprint_meta={'selected_pages':len(self.sparse_pages),'selected_bytes':len(self.sparse_pages)*0x1000,'original_regions':len(original),'original_bytes':sum(b-a+1 for a,b,p in original)}
    def sparse_info(self):return self.footprint_meta

if __name__=='__main__':
    o=SparseCapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
    print(json.dumps(o.sparse_info(),indent=2))
