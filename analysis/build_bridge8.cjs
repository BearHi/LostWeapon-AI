const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const originals=fs.readdirSync('.').filter(f=>/\.lmf$/i.test(f));const hashes=Object.fromEntries(originals.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')]));
const base=JSON.parse(fs.readFileSync('analysis/maps.json'))[1],spans=[[17,104],[131,194],[222,291],[318,390],[418,490]];
let blocks=base.blocks.filter(b=>![167,119,118].includes(b.id)&&!spans.some(([a,z])=>b.x>=a&&b.x<=z&&b.y>=8&&b.y<=14));let cells=new Map(blocks.map(b=>[b.x+','+b.y,b]));
function put(id,x,y){assert(x>=0&&x<500&&y>=0&&y<20);assert(!cells.has(x+','+y),'overlap '+x+','+y);let b={id,x,y};cells.set(x+','+y,b);blocks.push(b);}
function line(id,a,z,y){for(let x=a;x<=z;x++)put(id,x,y);}
function magnets(id,x){for(let dx=0;dx<3;dx++)put(id,x+dx,10);}
const stages=[];
// 1: three different-length acceleration stretches with fixed islands between them.
let seq1='F F F F Q F F F F F Q F F F F F F Q F F F F F F F F F F F F'.split(' ');
// 2: short opposed-force stretches, then alternating left/right force; no spike hazards.
let seq2='F F F F Q F F F F F F Q F F F F F Q F F F F'.split(' ');
// 4: momentum on vanishing landings, interrupted by wider stable islands.
let seq4='F D D D F F Q F D D D D F F Q F D D F D D F D F F'.split(' ');
// 5: direction changes and a few timed spikes. Still no random block palette.
let seq5='F F D D F Q F F T F D D F Q F D F T F D D F T F F'.split(' ');
const sets=[seq1,seq2,null,seq4,seq5];
for(let s=0;s<5;s++){
 let [a,z]=spans[s],rests=[],pads=[];
 if(s===2){
  // Entire span is contiguous: jump suppression can never strand the player across a missing gap.
  // Green disappearing runs are separated by permanent four-cell islands.
  const safe=[[222,228],[244,248],[265,269],[287,291]];
  for(let x=a;x<=z;x++){let fixed=safe.some(([l,r])=>x>=l&&x<=r);put(fixed?62:124,x,9);pads.push({x,y:9,id:fixed?62:124});}
  for(let [l,r] of safe)rests.push({x:l,y:9,width:r-l+1});
  // 5x5 rule zones sit fully inside contiguous running strips.
  for(let x of [233,238,254,259,275,280])put(136,x,8);
  magnets(54,234);magnets(55,256);magnets(54,277);
 }else{
  let seq=sets[s],n=Math.floor((z-a)/3)+1;assert.equal(seq.length,n,'length '+s);
  seq.forEach((t,i)=>{let x=a+3*i,id=t==='D'?124:62;put(id,x,9);pads.push({id,x,y:9});if(t==='Q'){line(62,x+1,x+2,9);rests.push({x,y:9,width:3});}if(t==='T')put(119,x,8);});
 }
 stages.push({stage:s+1,range:[a,z],rests,pads});
}
for(let x of [20,38,59,83])magnets(54,x);
for(let x of [134,155,176])magnets(55,x);magnets(54,185);
for(let x of [321,348,372])magnets(54,x);
for(let x of [421,460])magnets(54,x);for(let x of [442,478])magnets(55,x);
const file='다리건너기8_자력회랑.LMF';let h=Buffer.from(fs.readFileSync('다리건너기1.LMF').subarray(0,32));h.writeUInt32LE(blocks.length,21);let out=Buffer.alloc(32+blocks.length*8);h.copy(out);blocks.forEach((b,i)=>{let p=32+i*8;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6);});
fs.writeFileSync(file,out);let d=fs.readFileSync(file);assert.equal(d.length,32+d.readUInt32LE(21)*8);for(let i=0;i<blocks.length;i++){let p=32+i*8;assert.deepStrictEqual({id:d.readUInt32LE(p),x:d.readInt16LE(p+4),y:d.readInt16LE(p+6)},blocks[i]);}
for(let s of stages){assert(s.rests.length>=2);for(let i=1;i<s.pads.length;i++)assert(s.pads[i].x-s.pads[i-1].x<=3);}
for(let b of blocks.filter(b=>b.id===136))for(let x=b.x-3;x<=b.x+3;x++)assert([62,124].includes(cells.get(x+',9')?.id),'jump restriction bridge gap');
for(let [f,hash]of Object.entries(hashes))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),hash);
let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;fs.writeFileSync('analysis/bridge8_maps.json',JSON.stringify([{name:file,width:500,height:20,blocks,counts}]));
fs.writeFileSync('analysis/bridge8_validation.json',JSON.stringify({file,checks:['binary roundtrip','bounds and no duplicate coordinates','prior maps unchanged','route spacing <= reference','at least 2 rest islands per stage','continuous floor around every jump prohibition marker'],stages,limitation:'Horizontal magnet range/strength, combined gravity, disappearance timing and complete route require in-game testing.'},null,2));console.log({file,blocks:blocks.length,checks:'PASS'});
