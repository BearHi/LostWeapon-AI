const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const sources=['다리건너기.LMF','다리건너기1.LMF'];const before=sources.map(f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'));
const base=JSON.parse(fs.readFileSync('analysis/maps.json'))[1];
const spans=[[17,104],[131,194],[222,291],[318,390],[418,490]];
// Retain source launch bays, transitions, return lane, magnets, water and spawn points.
let blocks=base.blocks.filter(b=>b.id!==167&&!spans.some(([a,z])=>b.x>=a&&b.x<=z&&b.y>=8&&b.y<=14));
const cells=new Map(blocks.map(b=>[`${b.x},${b.y}`,b]));
function put(id,x,y){assert(!cells.has(`${x},${y}`),`occupied ${x},${y}`);let b={id,x,y};cells.set(`${x},${y}`,b);blocks.push(b);}
let stages=[];
for(let s=0;s<spans.length;s++){
 let [a,z]=spans[s],pads=[];
 for(let x=a,i=0;x<=z;x+=3,i++){
  let id=62,y=s===0?8:9;
  if(s===0){id=i%6===5?61:62;}
  if(s===1){id=i%6<3?19:62;}
  if(s===2){id=[62,19,27,62,19,27][i%6];}
  if(s===3){id=i%5===3?19:62;}
  if(s===4){id=[62,19,27,62,90,62,19,27][i%8];}
  put(id,x,y);pads.push({x,y,id});
  // Small double-width rest pads punctuate stage 1; no larger gaps than the reference.
  if(s===0&&i%6===0&&x<z)put(62,x+1,y);
  if(s===3&&i%6===3)put(119,x,y-1);
  if(s===4&&i%8===5)put(119,x,y-1);
  if(s===4&&i%8===7)put(118,x,14);
 }
 stages.push({stage:s+1,range:[a,z],pads,concept:['일반 발판 리듬 익히기','일반 발판과 미끄러운 얼음 교대','사각 얼음과 경사 얼음 조합','일반 발판 위 가시 간헐 배치','얼음, 경사, 별 얼음, 가시와 용암 종합'][s]});
}
const src=fs.readFileSync(sources[1]);const header=Buffer.from(src.subarray(0,32));header[20]=18;header.writeUInt32LE(blocks.length,21);
const out=Buffer.alloc(32+blocks.length*8);header.copy(out);blocks.forEach((b,i)=>{let o=32+i*8;out.writeUInt32LE(b.id,o);out.writeInt16LE(b.x,o+4);out.writeInt16LE(b.y,o+6);});
fs.writeFileSync('다리건너기2.LMF',out);
const read=fs.readFileSync('다리건너기2.LMF');assert.equal(read.length,32+read.readUInt32LE(21)*8);assert.equal(read.subarray(0,16).toString(),'NewLWMapFile_1.0');
let decoded=[];for(let o=32;o<read.length;o+=8)decoded.push({id:read.readUInt32LE(o),x:read.readInt16LE(o+4),y:read.readInt16LE(o+6)});assert.deepStrictEqual(decoded,blocks);
assert(blocks.every(b=>b.x>=0&&b.x<500&&b.y>=0&&b.y<20));assert.equal(cells.size,blocks.length);
for(let id=100;id<=109;id++)assert.equal(blocks.filter(b=>b.id===id).length,1);
const foundation=b=>b.y>=15||b.y<=7;assert.deepStrictEqual(blocks.filter(foundation),base.blocks.filter(b=>b.id!==167).filter(foundation));
for(let s of stages)for(let i=1;i<s.pads.length;i++)assert(s.pads[i].x-s.pads[i-1].x<=3);
assert.deepStrictEqual(before,sources.map(f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')));
let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;
fs.writeFileSync('analysis/bridge2_maps.json',JSON.stringify([{name:'다리건너기2.LMF',width:500,height:20,background:18,count:blocks.length,counts,blocks}]));
fs.writeFileSync('analysis/bridge2_validation.json',JSON.stringify({file:'다리건너기2.LMF',bytes:out.length,count:blocks.length,sourceHashes:before,checks:['binary round trip','bounds','no duplicate cells','10 spawn markers','source foundation preserved excluding unsupported ID 167','reference pad spacing retained','source files unchanged'],stages,limitation:'에디터 및 인게임 로드, 실제 통과 가능 여부는 미검증'},null,2));
console.log(JSON.stringify({file:'다리건너기2.LMF',bytes:out.length,blocks:blocks.length,counts,checks:'passed'}));
