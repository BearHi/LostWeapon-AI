const fs=require('fs');const src=fs.readFileSync('영상/용암.LMF');const W=100,H=100,c=new Map();const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)c.set(`${x},${y}`,{id,x,y})};const rect=(id,a,b,d,e)=>{for(let y=b;y<=e;y++)for(let x=a;x<=d;x++)put(id,x,y)};const clear=(a,b,d,e)=>{for(let y=b;y<=e;y++)for(let x=a;x<=d;x++)c.delete(`${x},${y}`)};
// irregular cave walls, leaving central air route
rect(8,0,0,99,5);rect(8,0,0,5,99);rect(8,94,0,99,99);for(const q of [[0,12,24,28],[33,8,58,20],[68,8,93,27],[8,34,28,53],[40,30,65,48],[75,38,99,59],[0,68,25,86],[35,62,57,80],[68,70,94,91]])rect(8,...q);
// lava basins beneath and beside route
for(const q of [[6,91,35,97],[25,82,45,87],[42,70,62,75],[57,57,82,62],[70,43,95,48],[40,25,55,30],[13,54,30,59]])rect(49,...q);
// continuous stepped route made of walkable light-rock platforms
rect(7,7,89,22,90);rect(7,18,83,28,84);rect(7,24,76,35,77);rect(7,31,43,69,70);rect(7,40,50,49,51);rect(7,47,55,60,56);rect(7,58,64,69,65);rect(7,67,70,79,71);rect(7,77,76,88,77);rect(7,86,84,96,85);
// stair connectors
rect(7,22,84,25,89);rect(7,35,69,39,76);rect(7,49,50,53,55);rect(7,60,56,64,64);rect(7,69,65,73,70);rect(7,79,71,83,76);rect(7,88,77,92,84);
// clear air above the route
for(const q of [[7,70,22,88],[19,64,31,82],[30,53,44,75],[44,43,58,69],[55,32,70,55],[67,22,83,48],[78,10,92,38]])clear(...q);
// rebuild route platforms after clears
rect(7,7,89,22,90);rect(7,18,83,28,84);rect(7,24,35,77);rect(7,31,43,69,70);rect(7,40,50,49,51);rect(7,47,55,60,56);rect(7,58,64,69,65);rect(7,67,70,79,71);rect(7,77,76,88,77);rect(7,86,84,96,85);
// start and visible route markers / mechanics
put(100,10,88);put(4,21,82);put(136,34,68);put(4,48,49);put(142,61,64);put(136,78,76);for(const p of [[16,88],[27,82],[38,68],[52,55],[66,64],[82,76]])put(86,...p);
// decorative number markers, not gameplay requirement
for(const p of [[20,82],[35,68],[50,49],[63,64],[80,76],[91,84]])put(100+(p[0]%10),...p);
let rec=[...c.values()],out=Buffer.from(src.subarray(0,32));out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(rec.length,21);for(const b of rec){let q=Buffer.alloc(8);q.writeUInt32LE(b.id);q.writeInt16LE(b.x,4);q.writeInt16LE(b.y,6);out=Buffer.concat([out,q])}fs.writeFileSync('지옥_새설계1.LMF',out);console.log(rec.length,out.length)
