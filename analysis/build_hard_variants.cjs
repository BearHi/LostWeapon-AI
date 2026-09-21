const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const originals=['다리건너기.LMF','다리건너기1.LMF','다리건너기2.LMF','다리건너기3.LMF'];const hashes=originals.map(f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'));
const maps=[],reports=[];
const variants=[{file:'다리건너기4_소멸연타.LMF',width:500,mode:0},{file:'다리건너기5_스프링연쇄.LMF',width:500,mode:1},{file:'다리건너기6_소멸복합.LMF',width:600,mode:2}];
for(const v of variants){
 const W=v.width,blocks=[],cells=new Map(),pads=[];
 function put(id,x,y){assert(x>=0&&x<W&&y>=0&&y<20);assert(!cells.has(x+','+y),'overlap '+v.file+' '+x+','+y);let b={id,x,y};blocks.push(b);cells.set(x+','+y,b);}
 function line(id,a,z,y){for(let x=a;x<=z;x++)put(id,x,y);}
 // Same upper/lower downward magnets and submerged leftward spring return lane as references.
 line(52,0,W-1,7);line(52,7,W-1,15);line(123,1,W-1,19);line(4,1,6,18);line(6,7,W-1,18);
 for(let y=8;y<=18;y++)put(62,0,y);line(62,1,6,8);line(62,1,6,13);
 for(let i=0;i<10;i++)put(100+i,i,5);
 // No mid-course fixed rest islands, no lower catch platforms, no checkpoint markers.
 for(let x=9,i=0;x<W-8;x+=3,i++){
  let id=124,y=9;
  if(v.mode===0){
   // All playable route pads disappear. Increasing density of retracting spikes.
   if(x>105&&i%(x>340?3:5)===1)put(119,x,y-1);
  }else if(v.mode===1){
   id=62;y=9;
   // Bare rightward springs alternate with mandatory small landings; leftward springs late in course counter momentum.
   if(i%4===1){id=(x>300&&i%12===9)?6:5;}
   if(i%4===3&&x>90)put(119,x,y-1);
  }else{
   // Disappearing landings, directional springs, one-cell height changes, then reset hazards below selected pads.
   const wave=[9,9,10,10,9,9,10,9];y=wave[i%8];
   if(i%8===2)id=5;
   if(x>120&&i%8===5)put(119,x,y-1);
   if(x>310&&i%8===7)put(118,x,14);
   if(x>450&&i%8===6)id=6;
  }
  put(id,x,y);pads.push({id,x,y});
 }
 // Small final ledge; avoid adding recovery shelves along the course.
 line(62,W-7,W-1,9);put(142,W-3,8);
 // Upper progress numerals, physically separated from gameplay by the magnet row.
 const font={'1':['010','110','010','010','111'],'2':['110','001','010','100','111'],'3':['110','001','010','001','110'],'4':['101','101','111','001','001'],'5':['111','100','110','001','110'],'6':['011','100','111','101','111']};
 for(let x=35,n=1;x<W-15;x+=100,n++){let g=font[String(n)];if(!g)continue;g.forEach((row,y)=>[...row].forEach((c,dx)=>{if(c==='1')put(82,x+dx,y+1);}));}
 let h=Buffer.from(fs.readFileSync('다리건너기1.LMF').subarray(0,32));h.writeUInt16LE(W,16);h.writeUInt16LE(20,18);h.writeUInt32LE(blocks.length,21);
 let out=Buffer.alloc(32+blocks.length*8);h.copy(out);blocks.forEach((b,i)=>{let p=32+i*8;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6);});fs.writeFileSync(v.file,out);
 let d=fs.readFileSync(v.file);assert.equal(d.length,32+d.readUInt32LE(21)*8);assert.equal(d.readUInt16LE(16),W);
 for(let i=0;i<blocks.length;i++){let p=32+i*8,b=blocks[i];assert.equal(d.readUInt32LE(p),b.id);assert.equal(d.readInt16LE(p+4),b.x);assert.equal(d.readInt16LE(p+6),b.y);}
 for(let i=1;i<pads.length;i++){assert(pads[i].x-pads[i-1].x<=3);assert(Math.abs(pads[i].y-pads[i-1].y)<=1);}
 assert.equal(blocks.filter(b=>b.id>=100&&b.id<=109).length,10);assert.equal(blocks.filter(b=>b.id===123).length,W-1);
 let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;
 maps.push({name:v.file,width:W,height:20,blocks,counts});reports.push({file:v.file,width:W,blocks:blocks.length,routePads:pads.length,counts,validation:'binary round-trip, unique coordinates, bounds, 10 spawns, pad dx<=3 dy<=1 passed',playtest:'NOT RUN: spring trajectory, disappearance/spike timing, return lane behavior and complete traversal require game testing'});
}
assert.deepStrictEqual(hashes,originals.map(f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')));
fs.writeFileSync('analysis/hard_variants_maps.json',JSON.stringify(maps));fs.writeFileSync('analysis/hard_variants_validation.json',JSON.stringify(reports,null,2));console.log(JSON.stringify(reports,null,2));
