const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync('analysis/bridge8_wall_revision_pending.LMF');let blocks=[];for(let p=32;p<source.length;p+=8)blocks.push({id:source.readUInt32LE(p),x:source.readInt16LE(p+4),y:source.readInt16LE(p+6)});
let horizontal=blocks.filter(b=>b.id===54||b.id===55).sort((a,b)=>a.x-b.x),groups=[];
for(let i=0;i<horizontal.length;i+=3){let a=horizontal.slice(i,i+3);assert.equal(a.length,3);assert(a.every((b,k)=>b.id===a[0].id&&b.x===a[0].x+k&&b.y===10));groups.push({id:a[0].id,x:a[0].x});}
for(let g of groups){if(blocks.some(b=>b.x===g.x&&b.y>=6&&b.y<=8&&b.id!==52)){let x=g.x-3;assert(blocks.some(b=>b.x===x&&b.y===9&&b.id===0));assert(!blocks.some(b=>b.x===x&&b.y>=6&&b.y<=8&&b.id!==52));g.x=x;}}
// Match the user's reference: three vertically stacked sideways magnets immediately above the platform.
// Remove the downward magnet in the same column so the reference stack fits without overlapping blocks.
blocks=blocks.filter(b=>![54,55].includes(b.id)&&!(b.id===52&&b.y===7&&groups.some(g=>g.x===b.x)));
let cells=new Map(blocks.map(b=>[b.x+','+b.y,b]));for(let g of groups){assert.equal(cells.get(g.x+',9')?.id,0,'support missing '+g.x);for(let y=6;y<=8;y++){assert(!cells.has(g.x+','+y),'occupied '+g.x+','+y);let b={id:g.id,x:g.x,y};cells.set(g.x+','+y,b);blocks.push(b);}}
const file='다리건너기8_자력회랑.LMF';let header=Buffer.from(source.subarray(0,32));header.writeUInt32LE(blocks.length,21);let out=Buffer.alloc(32+8*blocks.length);header.copy(out);blocks.forEach((b,i)=>{let p=32+8*i;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6);});
assert.equal(cells.size,blocks.length);assert(blocks.every(b=>b.x>=0&&b.x<500&&b.y>=0&&b.y<20));
fs.writeFileSync(file,out);let d=fs.readFileSync(file);assert.equal(d.length,32+8*d.readUInt32LE(21));for(let i=0;i<blocks.length;i++){let p=32+i*8;assert.deepStrictEqual({id:d.readUInt32LE(p),x:d.readInt16LE(p+4),y:d.readInt16LE(p+6)},blocks[i]);}
let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;fs.writeFileSync('analysis/bridge8_maps.json',JSON.stringify([{name:file,width:500,height:20,blocks,counts}]));
fs.writeFileSync('analysis/bridge8_magnet_correction.json',JSON.stringify({file,groups,reference:'Three vertically stacked sideways magnets directly over the supporting tile, matching user screenshot. Intersecting downward magnet removed.',checks:['binary roundtrip','unique coordinates','bounds','each stack immediately above a fixed platform'],limitation:'In-game force and route traversal not tested.'},null,2));console.log({file,stacks:groups.length,blocks:blocks.length,checks:'PASS'});

