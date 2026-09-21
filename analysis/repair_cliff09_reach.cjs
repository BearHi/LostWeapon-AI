const fs=require('fs');
const src=fs.readFileSync('암벽_깎인능선09.LMF'),W=31,H=240,m=new Map();
for(let p=32;p<src.length;p+=8){const r={id:src.readUInt32LE(p),x:src.readInt16LE(p+4),y:src.readInt16LE(p+6)};m.set(`${r.x},${r.y}`,r)}
// Explicit feet-on-surface coordinates, bottom to top. These are design targets,
// not claimed video measurements or game-physics simulation results.
const route=[[12,239],[11,233],[17,228],[9,224],[20,219],[24,214],[21,210],[11,205],[6,200],[10,195],[18,191],[9,185],[14,179],[21,173],[25,168],[15,163],[17,158],[17,153],[10,148],[7,143],[15,138],[22,133],[14,128],[9,128],[17,123],[20,118],[16,113],[11,109],[19,104],[25,99],[17,94],[7,89],[18,85],[18,80],[25,75],[16,70],[10,70],[16,65],[12,60],[10,55],[7,50],[16,45],[14,40],[10,37],[20,34],[20,29],[13,24],[11,20],[17,16],[23,12],[18,7],[12,3]];
const put=(id,x,y)=>m.set(`${x},${y}`,{id,x,y});let added=0;
// Preserve existing terrain. Add narrow wall noses only where a route foot is absent.
for(const [x,y] of route){
 if(m.get(`${x},${y}`)?.id===8)continue;
 const side=x<15?'L':'R';
 for(let dy=0;dy<2;dy++){
 const start=side==='L'?0:x+dy,end=side==='L'?x-dy:W-1;
 for(let xx=start;xx<=end;xx++)if(!m.has(`${xx},${y+dy}`)){put(8,xx,y+dy);added++}
 }
}
// Remove old hazards from this reach-repair version; a forced damage step must not
// be mistaken for a verified movement connection.
for(const [k,r] of m)if(r.id===119)m.delete(k);
// Clear the standing body at each explicit takeoff/landing point.
let cleared=0;for(const [x,y] of route)for(let dy=1;dy<=2;dy++){if(m.get(`${x},${y-dy}`)?.id===8){m.delete(`${x},${y-dy}`);cleared++}}
const steps=route.slice(1).map((r,i)=>({from:route[i],to:r,rise:route[i][1]-r[1],horizontal:Math.abs(route[i][0]-r[0])}));
for(const [x,y] of route)if(m.get(`${x},${y}`)?.id!==8||m.get(`${x},${y-1}`)?.id===8||m.get(`${x},${y-2}`)?.id===8)throw Error('Invalid landing '+x+','+y);
if(steps.some(s=>s.rise>6))throw Error('Excessive design rise');
const records=[...m.values()],out=Buffer.alloc(32+8*records.length);src.copy(out,0,0,32);out.writeUInt32LE(records.length,21);records.forEach((r,i)=>{let p=32+8*i;out.writeUInt32LE(r.id,p);out.writeInt16LE(r.x,p+4);out.writeInt16LE(r.y,p+6)});
fs.writeFileSync('암벽_깎인능선09_연결수정.LMF',out);
fs.writeFileSync('analysis/cliff09_repaired.json',JSON.stringify({w:W,h:H,records,route,steps,checks:{added,cleared,maxRise:Math.max(...steps.map(s=>s.rise)),maxHorizontal:Math.max(...steps.map(s=>s.horizontal)),landingSupport:true,standingClearance:true,trajectoryCollision:'not verified',runtime:'not tested'}}));
console.log(JSON.stringify({added,cleared,steps:steps.length,maxRise:Math.max(...steps.map(s=>s.rise)),maxHorizontal:Math.max(...steps.map(s=>s.horizontal))}));

