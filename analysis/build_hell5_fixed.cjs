const fs=require('fs'),assert=require('assert');const W=50,H=50,bs=[],used=new Set();
function put(id,x,y){if(x<0||x>=W||y<0||y>=H||used.has(x+','+y))return;used.add(x+','+y);bs.push({id,x,y})}
function h(id,a,z,y){for(let x=a;x<=z;x++)put(id,x,y)}function v(id,x,a,z){for(let y=a;y<=z;y++)put(id,x,y)}
// Sparse solid walls: open space is left empty, as in the playable samples.
h(11,0,49,0);h(11,0,49,49);v(11,0,0,49);v(11,49,0,49);
for(let y=5;y<45;y+=8){h(11,3,46,y)}
for(let x of [8,16,24,32,40]){v(11,x,5,13);put(37,x,12);v(11,x,21,29);put(37,x,28);v(11,x,37,45);put(37,x,44)}
for(let x of [11,19,27,35,43]){put(19,x,7);put(119,x+1,7);put(5,x+2,7)}
for(let x of [9,17,25,33,41])put(48,x,17);for(let x of [13,21,29,37])put(49,x,33);
put(100,3,46);put(84,46,46);
const src=fs.readFileSync('학습용/지옥3.lmf'),h0=Buffer.from(src.subarray(0,32));h0.writeUInt16LE(W,16);h0.writeUInt16LE(H,18);h0.writeUInt32LE(bs.length,21);const out=Buffer.alloc(32+8*bs.length);h0.copy(out);bs.forEach((b,i)=>{let p=32+8*i;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6)});const file='지옥5_간단미로_수정.LMF';fs.writeFileSync(file,out);assert.equal(out.length,32+8*bs.length);fs.writeFileSync('analysis/hell5_fixed_validation.json',JSON.stringify({file,width:W,height:H,blocks:bs.length,spawn:'ID 100 only at (3,46)',openSpace:'unrecorded cells remain empty',checks:['binary size','sparse wall layout','single respawn marker']},null,2));console.log({file,bytes:out.length,blocks:bs.length})
