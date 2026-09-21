const fs=require('fs');const src=fs.readFileSync('영상/용암.LMF');const W=80,H=60,c=new Map();const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)c.set(`${x},${y}`,{id,x,y})};const clear=(a,b,d,e)=>{for(let y=b;y<=e;y++)for(let x=a;x<=d;x++)c.delete(`${x},${y}`)};const blob=(id,cx,cy,rx,ry)=>{for(let y=cy-ry;y<=cy+ry;y++)for(let x=cx-rx;x<=cx+rx;x++){let q=((x-cx)/(rx||1))**2+((y-cy)/(ry||1))**2;if(q<1&&((x*13+y*7)%5!==0))put(id,x,y)}};const platform=(x,y,w)=>{for(let i=0;i<w;i++)put(7,x+i,y);for(let i=0;i<w;i++)if(i%3===0)put(7,x+i,y+1)};
// irregular rock masses, leaving open air corridors
for(const q of [[9,45,10,7],[27,39,12,8],[17,27,9,7],[37,24,12,7],[55,35,13,8],[67,22,10,8],[57,12,13,7],[27,10,10,6],[70,48,9,8],[11,12,8,6]])blob(8,...q);
// lava pools/rivers with uneven edges
for(const q of [[2,55,24,4],[19,48,9,3],[30,42,18,3],[43,50,20,3],[58,42,18,4],[69,29,8,10],[47,19,6,12],[25,18,8,3]])blob(49,...q);
// clear intended route corridor
for(const q of [[3,49,15,54],[15,43,24,49],[20,34,31,43],[10,25,20,35],[19,20,35,29],[31,14,43,22],[40,18,55,28],[53,25,66,36],[63,14,75,27],[69,5,77,17]])clear(...q);
// route platforms, varied sizes
platform(4,52,10);platform(18,44,8);platform(25,36,7);platform(12,28,8);platform(22,22,10);platform(35,16,9);platform(48,26,8);platform(60,33,8);platform(68,22,8);platform(72,9,6);
// hazards and mechanics on route edges
for(const p of [[10,51],[22,43],[29,35],[17,27],[29,21],[41,15],[54,25],[66,32],[74,21]])put(86,...p);
put(4,12,51);put(4,24,43);put(136,31,35);put(136,57,32);put(142,64,32);
// spawn and numbered route markers
put(100,5,51);put(101,20,43);put(102,27,35);put(103,14,27);put(104,24,21);put(105,37,15);put(106,50,25);put(107,62,32);put(108,70,21);put(109,73,8);
let rec=[...c.values()],out=Buffer.from(src.subarray(0,32));out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(rec.length,21);for(const b of rec){let q=Buffer.alloc(8);q.writeUInt32LE(b.id);q.writeInt16LE(b.x,4);q.writeInt16LE(b.y,6);out=Buffer.concat([out,q])}fs.writeFileSync('용암6_화산협곡.LMF',out);console.log(rec.length,out.length)
