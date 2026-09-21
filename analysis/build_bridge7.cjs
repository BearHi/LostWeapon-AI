const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const originals=fs.readdirSync('.').filter(f=>/\.lmf$/i.test(f));const hashes=Object.fromEntries(originals.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')]));
const base=JSON.parse(fs.readFileSync('analysis/maps.json'))[1];
const spans=[[17,104],[131,194],[222,291],[318,390],[418,490]];
// Hand-authored sequences. F fixed, D disappearing, I ice, R ice slope,
// S supported directional spring, T retracting spike, Q fixed 3-cell rest.
// Every stage has several different short phrases instead of a repeated loop.
const plans=[
 {name:'사라지는 발판',seq:'F F D D F D D D Q F D D F D D D D Q F D F D D D F D D D F F',phrases:['짧은 소멸 발판','연속 소멸 발판','길이가 달라지는 연속 구간']},
 {name:'얼음에서 멈추기',seq:'F I I F I R F Q I I R F I R I F Q I R I I F',phrases:['일반 발판에서 얼음 진입','경사 얼음에서 고정 발판 착지','얼음과 경사 교대']},
 {name:'스프링으로 연결',seq:'F S F F S F Q F S I F S F F Q F S F S F S F F F',phrases:['스프링 뒤 고정 착지','스프링에서 얼음 착지','짧은 스프링 연속 조작']},
 {name:'가시 타이밍',seq:'F F T F D F Q F T F T F Q F D T F D F Q F T D T F',phrases:['고정 발판에서 가시 관찰','두 가시 타이밍 맞추기','소멸 발판과 들낙가시']},
 {name:'세 가지 조합',seq:'F D D S F I F Q F T D F T F Q F I R S F D T D S F',phrases:['소멸 발판에서 스프링 연결','가시 사이 소멸 발판','얼음에서 스프링, 소멸 가시 연결']}
];
let blocks=base.blocks.filter(b=>b.id!==167&&b.id!==119&&b.id!==118&&!spans.some(([a,z])=>b.x>=a&&b.x<=z&&b.y>=8&&b.y<=14));
const cells=new Map(blocks.map(b=>[b.x+','+b.y,b]));function put(id,x,y){assert(x>=0&&x<500&&y>=0&&y<20);assert(!cells.has(x+','+y),'occupied '+x+','+y);let b={id,x,y};cells.set(x+','+y,b);blocks.push(b);}
let stages=[];
for(let s=0;s<5;s++){
 let [a,z]=spans[s],tokens=plans[s].seq.split(' '),needed=Math.floor((z-a)/3)+1;assert.equal(tokens.length,needed,'pattern length stage '+(s+1));
 let pads=[],rests=[];
 tokens.forEach((token,i)=>{let x=a+i*3,y=s===0?8:9,id=({D:124,I:19,R:27})[token]||62;
  put(id,x,y);pads.push({id,x,y,token});
  if(token==='S')put(5,x,y-1);
  if(token==='T')put(119,x,y-1);
  if(token==='Q'){put(62,x+1,y);put(62,x+2,y);rests.push({x,y,width:3});}
 });
 assert(rests.length>=2);for(let i=1;i<pads.length;i++)assert(pads[i].x-pads[i-1].x<=3);
 stages.push({stage:s+1,name:plans[s].name,range:[a,z],phrases:plans[s].phrases,rests,pads});
}
const file='다리건너기7_기믹여행.LMF';let h=Buffer.from(fs.readFileSync('다리건너기1.LMF').subarray(0,32));h.writeUInt32LE(blocks.length,21);let out=Buffer.alloc(32+blocks.length*8);h.copy(out);
blocks.forEach((b,i)=>{let p=32+i*8;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6);});fs.writeFileSync(file,out);
let d=fs.readFileSync(file);assert.equal(d.length,32+d.readUInt32LE(21)*8);for(let i=0;i<blocks.length;i++){let p=32+i*8,b=blocks[i];assert.deepStrictEqual({id:d.readUInt32LE(p),x:d.readInt16LE(p+4),y:d.readInt16LE(p+6)},b);}assert.equal(blocks.length,cells.size);
for(let id=100;id<=109;id++)assert.equal(blocks.filter(b=>b.id===id).length,1);
for(let [f,hash]of Object.entries(hashes))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),hash);
let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;
fs.writeFileSync('analysis/bridge7_maps.json',JSON.stringify([{name:file,width:500,height:20,blocks,counts}]));
fs.writeFileSync('analysis/bridge7_validation.json',JSON.stringify({file,bytes:d.length,count:blocks.length,checks:['binary roundtrip','bounds and unique cells','source files unchanged','10 spawns','each stage >=2 intermediate rests','reference maximum horizontal pad spacing retained'],stages,limitation:'Actual disappearance timing, retracting spike timing, spring trajectory and clearability need in-game testing.'},null,2));
console.log(JSON.stringify({file,blocks:blocks.length,intermediateRests:stages.map(s=>s.rests.length),checks:'PASS'}));
