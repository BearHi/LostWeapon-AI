const fs=require('fs');
const src=fs.readFileSync('영상/용암.LMF'); const W=50,H=50; const cells=new Map();
const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)cells.set(`${x},${y}`,{id,x,y});};
const rect=(id,x1,y1,x2,y2)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)put(id,x,y)};
// outer ceiling and side walls
rect(8,0,0,49,1); rect(8,0,0,1,49); rect(8,48,0,49,49);
// lava basins under route
rect(49,2,46,47,49); rect(49,11,41,46,45); rect(49,21,36,46,40); rect(49,31,36,35,40);
// zig-zag safe platforms
rect(8,2,44,10,45); rect(8,14,39,21,40); rect(8,25,34,31,35); rect(8,35,29,41,30); rect(8,43,24,47,25);
// upper return platform / finish area
rect(8,38,18,47,19); rect(8,27,12,34,13); rect(8,14,7,22,8);
// short vertical walls to force route choices
rect(8,10,41,11,45); rect(8,21,36,22,40); rect(8,31,35,36,36); rect(8,41,20,42,29); rect(8,34,13,35,18); rect(8,22,8,23,13);
// springs at floor ends, jump pad, heal on actual floor
put(4,9,43); put(4,20,38); put(136,30,33); put(142,39,28);
// spikes at selected platform edges
put(86,15,38); put(86,29,33); put(86,44,23); put(86,28,11);
// respawn marker and numbered goal markers
put(100,4,43); put(101,18,37); put(102,29,32); put(103,39,27); put(104,18,6);
let rec=[...cells.values()]; let out=Buffer.from(src.subarray(0,32)); out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(rec.length,21);
for(const b of rec){let q=Buffer.alloc(8);q.writeUInt32LE(b.id,0);q.writeInt16LE(b.x,4);q.writeInt16LE(b.y,6);out=Buffer.concat([out,q]);}
fs.writeFileSync('용암4_지그재그기믹.LMF',out);
// SVG plan
let s=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 500 500"><rect width="500" height="500" fill="#202838"/>`;
for(const b of rec){let c=b.id===49?'#ef4b24':(b.id===86?'#eee':(b.id===4?'#c88b35':(b.id===136?'#24a9e8':(b.id===142?'#e33':'#76543b'))));s+=`<rect x="${b.x*10}" y="${b.y*10}" width="10" height="10" fill="${c}"/>`;}
s+=`<text x="8" y="20" fill="white" font-size="12">start → zigzag springs/jump → heal → upper finish</text></svg>`;fs.writeFileSync('analysis/용암4_설계도.svg',s); console.log('records',rec.length,'fileBytes',out.length);
