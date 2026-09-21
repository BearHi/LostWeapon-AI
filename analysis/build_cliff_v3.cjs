const fs=require('fs');
const src=fs.readFileSync('학습용/암벽11.LMF');const w=src.readUInt16LE(16),h=src.readUInt16LE(18),n=src.readUInt32LE(21),records=[];
for(let i=0;i<n;i++){let p=32+i*8;records.push({id:src.readUInt32LE(p),x:src.readInt16LE(p+4),y:src.readInt16LE(p+6)});}
const cells=new Map(records.map(r=>[`${r.x},${r.y}`,r]));
// Retain all original contact surfaces and interactive objects. Shape only added outer rock.
const out=records.map(r=>({...r,x:r.x+4}));
for(const r of out){if(r.id!==8)continue;const x=r.x-4;let buried=true;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)if(cells.get(`${x+dx},${r.y+dy}`)?.id!==8)buried=false;
if(buried&&Math.sin(x*.65+r.y*.13)+.45*Math.sin(r.y*.39-x*.2)>1.03)r.id=7;}
for(let y=0;y<h;y++)for(let side=0;side<2;side++){
const edge=cells.get(`${side?w-1:0},${y}`);if(!edge||edge.id!==8)continue;
const thickness=1+Math.round((Math.sin(y*.071+side*2)+1)*1.5);
for(let d=1;d<=thickness;d++)out.push({id:d===thickness?8:7,x:side?w+3+d:4-d,y});}
const b=Buffer.alloc(32+out.length*8);src.copy(b,0,0,32);b.writeUInt16LE(w+8,16);b.writeUInt32LE(out.length,21);out.forEach((r,i)=>{const p=32+i*8;b.writeUInt32LE(r.id,p);b.writeInt16LE(r.x,p+4);b.writeInt16LE(r.y,p+6)});
fs.writeFileSync('암벽_침식능선_v3.LMF',b);fs.writeFileSync('analysis/cliff_v3.json',JSON.stringify({w:w+8,h,records:out}));
// All source coordinates are retained, only solid rock 8 -> solid rock 7 is permitted.
for(let i=0;i<n;i++){const a=records[i],z=out[i];if(z.x!==a.x+4||z.y!==a.y||!(z.id===a.id||a.id===8&&z.id===7))throw Error('Source geometry changed');}
console.log(JSON.stringify({width:w+8,height:h,records:out.length,retainedSourceRecords:n,changedRockTiles:out.slice(0,n).filter((r,i)=>r.id!==records[i].id).length,spawn:out.filter(r=>r.id===100)}));
