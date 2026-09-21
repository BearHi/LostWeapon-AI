const fs=require('fs');const src=fs.readFileSync('암벽_연결루트_v6.LMF');const W=src.readUInt16LE(16),H=src.readUInt16LE(18),n=src.readUInt32LE(21),m=[];
for(let i=0;i<n;i++){let p=32+i*8;m.push({id:src.readUInt32LE(p),x:src.readInt16LE(p+4),y:src.readInt16LE(p+6)});}
const map=new Map(m.map(r=>[`${r.x},${r.y}`,r]));const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)map.set(`${x},${y}`,{id,x,y});};
// Connect the old anchors with continuous walkable slopes. No transition is higher than one cell.
const a=[[3,171],[15,158],[6,145],[16,132],[8,119],[18,106],[6,93],[15,80],[8,67],[17,54],[5,41],[14,28],[7,15]];
for(let i=0;i<a.length-1;i++){
 let [x,y]=a[i],[tx,ty]=a[i+1],steps=Math.max(Math.abs(tx-x),Math.abs(ty-y));
 for(let k=0;k<=steps;k++){
  const xx=Math.round(x+(tx-x)*k/steps), yy=Math.round(y+(ty-y)*k/steps);
  const id=(tx>x)?27:37; put(id,xx,yy); put(id,Math.max(0,Math.min(W-1,xx+(tx>x?-1:1))),yy+1);
 }
}
// Keep 2-cell headroom in the newly connected path.
for(const [x,y] of a)for(let d=1;d<=2;d++)map.delete(`${x},${y-d}`);
const out=[...map.values()],b=Buffer.alloc(32+out.length*8);src.copy(b,0,0,32);b.writeUInt32LE(out.length,21);out.forEach((r,i)=>{let p=32+i*8;b.writeUInt32LE(r.id,p);b.writeInt16LE(r.x,p+4);b.writeInt16LE(r.y,p+6)});fs.writeFileSync('암벽_연결루트_v7.LMF',b);fs.writeFileSync('analysis/cliff_v7.json',JSON.stringify({w:W,h:H,records:out}));console.log(`${W}x${H}, ${out.length} blocks`);
