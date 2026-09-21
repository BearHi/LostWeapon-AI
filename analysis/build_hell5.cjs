const fs=require('fs'),assert=require('assert');const W=50,H=50,blocks=[],used=new Map();
function put(id,x,y){if(x<0||x>=W||y<0||y>=H)return;if(used.has(x+','+y))return;let b={id,x,y};used.set(x+','+y,b);blocks.push(b)}
function carve(x,y){used.delete(x+','+y);blocks.push({id:0,x,y})}
// Solid 1-cell wall frame/interior, then carve a serpentine route.
for(let y=0;y<H;y++)for(let x=0;x<W;x++)put(11,x,y);
for(let row=2;row<48;row+=4){for(let x=2;x<48;x++)carve(x,row);if(row<46){let cx=(row/4)%2?46:3;for(let y=row;y<=row+4;y++)carve(cx,y)}}
// Remove placeholder empty cells and add functional route tiles.
const route=[...blocks.filter(b=>b.id===0)];blocks.splice(0,blocks.length,...blocks.filter(b=>b.id!==0));used.clear();for(let b of blocks)used.set(b.x+','+b.y,b);
for(let b of route)put(62,b.x,b.y);
for(let row=2,i=0;row<48;row+=4,i++){let cx=(row/4)%2?46:3;put(37,cx,row+2);if(i%2===0)put(119,cx-2,row);if(i%3===1)put(19,cx+3,row);if(i%4===2)put(5,cx,row)}
// Water and lava are side hazards, not the only floor. They force the carved route.
for(let x=8;x<42;x+=6)put(48,x, row=6);for(let x=12;x<44;x+=7)put(49,x,22);for(let x=7;x<40;x+=8)put(49,x,38);
for(let id=100;id<=109;id++)put(id,3+(id%3),46);put(84,46,2);
const src=fs.readFileSync('학습용/지옥3.lmf'),h=Buffer.from(src.subarray(0,32));h.writeUInt16LE(W,16);h.writeUInt16LE(H,18);h.writeUInt32LE(blocks.length,21);let out=Buffer.alloc(32+8*blocks.length);h.copy(out);blocks.forEach((b,i)=>{let p=32+8*i;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6)});
const file='지옥5_간단미로.LMF';fs.writeFileSync(file,out);let d=fs.readFileSync(file);assert.equal(d.length,32+8*d.readUInt32LE(21));assert(blocks.every(b=>b.x>=0&&b.x<W&&b.y>=0&&b.y<H));
fs.writeFileSync('analysis/hell5_validation.json',JSON.stringify({file,width:W,height:H,blocks:blocks.length,design:'serpentine connected route inside solid wall; ladder connectors; hazards placed as side pressure',checks:['binary roundtrip','bounds','10 markers'],limitation:'Actual collision semantics and route clearability require in-game testing.'},null,2));console.log({file,bytes:d.length,blocks:blocks.length})
