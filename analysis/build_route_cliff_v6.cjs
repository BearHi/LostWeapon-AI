const fs=require('fs');const src=fs.readFileSync('암벽_연결루트_v5.LMF');const W=src.readUInt16LE(16),H=src.readUInt16LE(18),n=src.readUInt32LE(21),m=[];
for(let i=0;i<n;i++){let p=32+i*8;m.push({id:src.readUInt32LE(p),x:src.readInt16LE(p+4),y:src.readInt16LE(p+6)});}
const key=(x,y)=>`${x},${y}`;const map=new Map(m.map(r=>[key(r.x,r.y),r]));
// Remove the scattered test devices from v5; place devices only at route transitions.
for(const [k,r] of map)if([4,19,51,86,118,119,122].includes(r.id))map.delete(k);
const put=(id,x,y)=>map.set(key(x,y),{id,x,y});
// Section A: spring launches from the low left anchor to the high right anchor.
put(4,10,159);for(let d=1;d<=4;d++)map.delete(key(10,159-d));
// Section B: ice landing makes the player slide toward the next right-hand ledge.
for(let x=16;x<=20;x++)put(19,x,132);
// Section C: two disappearing lips are the short timing crossing; no solid support underneath.
for(const [x,y] of [[8,119],[9,119]]){put(122,x,y);for(let d=1;d<=3;d++)map.delete(key(x,y+d));}
// Section D: fan below the open chamber is useful only with parachute recovery.
put(51,12,106);put(51,13,106);
// Section E: hazards shape the approach to the next landing rather than block the route.
put(86,22,93);put(86,2,80);put(86,22,28);
put(119,20,93);put(119,4,41);
put(118,21,67);put(118,3,15);
const a=[...map.values()];const out=Buffer.alloc(32+a.length*8);src.copy(out,0,0,32);out.writeUInt32LE(a.length,21);a.forEach((r,i)=>{let p=32+i*8;out.writeUInt32LE(r.id,p);out.writeInt16LE(r.x,p+4);out.writeInt16LE(r.y,p+6)});fs.writeFileSync('암벽_연결루트_v6.LMF',out);fs.writeFileSync('analysis/cliff_v6.json',JSON.stringify({w:W,h:H,records:a}));console.log(`${W}x${H}, ${a.length} blocks`);
