const fs=require('fs'),assert=require('assert');
const base=JSON.parse(fs.readFileSync('analysis/maps.json'))[1];
const spans=[[17,104],[131,194],[222,291],[318,390],[418,490]];
let blocks=base.blocks.filter(b=>b.id!==167&&!spans.some(([a,z])=>b.x>=a&&b.x<=z&&b.y>=8&&b.y<=14));
const used=new Map(blocks.map(b=>[b.x+','+b.y,b]));
function put(id,x,y){assert(!used.has(x+','+y),`overlap ${x},${y}`);assert(x>=0&&x<500&&y>=0&&y<20);const b={id,x,y};used.set(x+','+y,b);blocks.push(b)}
function line(id,a,z,y){for(let x=a;x<=z;x++)if(!used.has(x+','+y))put(id,x,y)}
const stages=[];
for(let s=0;s<5;s++){
 const [a,z]=spans[s],pads=[],rests=[];
 for(let x=a,i=0;x<=z;x+=3,i++){
  let id=62,y=9;
  if(s===0) id=i%5===2?19:62;                 // ice control
  if(s===1) id=i%4<2?124:62;                  // disappearing pairs
  if(s===2) id=i%5===1?5:62;                  // spring launch, fixed landings
  if(s===3) id=i%6===3?27:(i%6===4?19:62);    // slope then ice
  if(s===4) id=[62,124,62,5,62,19,27,62][i%8]; // mixed finale
  put(id,x,y);pads.push({id,x,y});
  if(id===5) put(62,x+1,y);
  if(i%7===5){line(62,x+1,x+2,y);rests.push({x:x+1,y,width:2})}
  if((s===3||s===4)&&i%6===3)put(119,x,y-1);
 }
 stages.push({stage:s+1,rests,pads});
}
const file='다리건너기9_기믹혼합.LMF';let h=Buffer.from(fs.readFileSync('다리건너기1.LMF').subarray(0,32));h.writeUInt32LE(blocks.length,21);let out=Buffer.alloc(32+blocks.length*8);h.copy(out);
blocks.forEach((b,i)=>{let p=32+i*8;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.x*0+b.y,p+6)});fs.writeFileSync(file,out);
const d=fs.readFileSync(file);assert.equal(d.length,32+d.readUInt32LE(21)*8);for(let i=0;i<blocks.length;i++){let p=32+i*8;assert.equal(d.readUInt32LE(p),blocks[i].id);assert.equal(d.readInt16LE(p+4),blocks[i].x);assert.equal(d.readInt16LE(p+6),blocks[i].y)}
fs.writeFileSync('analysis/bridge9_maps.json',JSON.stringify([{name:file,width:500,height:20,blocks,counts:Object.fromEntries([...blocks.reduce((m,b)=>(m.set(b.id,(m.get(b.id)||0)+1),m),new Map())])}]));fs.writeFileSync('analysis/bridge9_validation.json',JSON.stringify({file,bytes:d.length,blocks:blocks.length,stages,checks:['binary roundtrip','bounds','unique coordinates','five distinct stage motifs']},null,2));console.log({file,bytes:d.length,blocks:blocks.length});
