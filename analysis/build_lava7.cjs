const fs=require('fs');const src=fs.readFileSync('영상/용암.LMF');const W=80,H=60,c=new Map();const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)c.set(`${x},${y}`,{id,x,y})};const rect=(id,a,b,d,e)=>{for(let y=b;y<=e;y++)for(let x=a;x<=d;x++)put(id,x,y)};const clear=(a,b,d,e)=>{for(let y=b;y<=e;y++)for(let x=a;x<=d;x++)c.delete(`${x},${y}`)};
// orthogonal rock chambers
for(const q of [[0,0,22,7],[27,0,52,5],[58,0,79,10],[0,14,14,28],[20,12,34,19],[43,9,58,17],[67,16,79,31],[0,34,18,47],[25,28,39,39],[48,31,63,45],[68,39,79,57],[7,51,27,59],[38,49,58,59]])rect(8,...q);
// lava pools, all orthogonal
rect(49,15,8,24,11);rect(49,35,6,42,12);rect(49,55,12,67,16);rect(49,13,29,24,33);rect(49,40,21,47,39);rect(49,60,30,67,35);rect(49,28,42,36,46);rect(49,3,52,13,6);
// carve a guaranteed continuous 3-cell route through the map
const pts=[[4,54],[4,44],[16,44],[16,36],[28,36],[28,25],[40,25],[40,18],[53,18],[53,25],[64,25],[64,36],[73,36],[73,27],[73,18],[73,8]];
for(let i=0;i<pts.length-1;i++){let [x,y]=pts[i],[u,v]=pts[i+1];if(x===u)rect(7,x-1,Math.min(y,v),x+1,Math.max(y,v));else rect(7,Math.min(x,u),y-1,Math.max(x,u),y+1)}
// clear one-cell air above route and add mechanics on floor
for(const [x,y] of pts)clear(x-1,y-2,x+1,y-1);put(100,4,52);put(4,10,43);put(136,27,34);put(142,51,16);put(86,16,43);put(86,40,24);put(86,63,24);put(86,72,26);
let rec=[...c.values()],out=Buffer.from(src.subarray(0,32));out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(rec.length,21);for(const b of rec){let q=Buffer.alloc(8);q.writeUInt32LE(b.id);q.writeInt16LE(b.x,4);q.writeInt16LE(b.y,6);out=Buffer.concat([out,q])}fs.writeFileSync('용암7_연결화산로.LMF',out);console.log(rec.length,out.length)
