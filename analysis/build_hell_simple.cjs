const fs=require('fs'),assert=require('assert');
const W=80,H=60,blocks=[],used=new Map();
function put(id,x,y){assert(x>=0&&x<W&&y>=0&&y<H);if(used.has(x+','+y))return;const b={id,x,y};used.set(x+','+y,b);blocks.push(b)}
function h(id,a,z,y){for(let x=a;x<=z;x++)put(id,x,y)}
function v(id,x,a,z){for(let y=a;y<=z;y++)put(id,x,y)}
h(11,1,78,1);h(11,1,78,58);v(11,1,1,58);v(11,78,1,58);
h(11,1,22,15);v(11,22,1,15);h(11,22,38,15);v(11,38,15,30);
for(let x=5;x<=18;x+=3)put(62,x,13);put(4,18,14);put(5,18,13);
h(11,22,38,30);h(48,23,37,44);for(let x=24;x<=36;x+=3)put(62,x,42);put(19,32,41);
h(11,38,60,15);v(11,60,15,44);h(11,60,78,44);for(let x=42;x<=56;x+=3)put(x%2?19:62,x,42);for(let x of [47,53,59])put(119,x,41);put(62,57,42);
for(let y=50;y>=20;y-=6){h(11,62,74,y);put(62,65,y-1);put(62,70,y-1);put(5,73,y-2)}
for(let x of [66,71,75])put(119,x,18);put(62,76,14);put(84,76,13);
for(let id=100;id<=109;id++)put(id,3+(id-100)%5,54);
const src=fs.readFileSync('학습용/지옥1.LMF'),head=Buffer.from(src.subarray(0,32));head.writeUInt16LE(W,16);head.writeUInt16LE(H,18);head.writeUInt32LE(blocks.length,21);
const out=Buffer.alloc(32+8*blocks.length);head.copy(out);blocks.forEach((b,i)=>{let p=32+8*i;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6)});
const file='지옥4_간단.LMF';fs.writeFileSync(file,out);const d=fs.readFileSync(file);assert.equal(d.length,32+8*d.readUInt32LE(21));for(let i=0;i<blocks.length;i++){let p=32+8*i;assert.equal(d.readUInt32LE(p),blocks[i].id);assert.equal(d.readInt16LE(p+4),blocks[i].x);assert.equal(d.readInt16LE(p+6),blocks[i].y)}
fs.writeFileSync('analysis/hell_simple_validation.json',JSON.stringify({file,width:W,height:H,blocks:blocks.length,rooms:['spring rise','water stepping','ice and retracting spikes','final climb'],checks:['binary roundtrip','bounds','unique coordinates','10 spawn markers'],limitation:'Actual route clearability needs in-game testing.'},null,2));console.log({file,bytes:d.length,blocks:blocks.length})
