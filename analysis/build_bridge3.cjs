const fs=require('fs'),assert=require('assert');
const blocks=[],cells=new Map(),W=216,H=20;function put(id,x,y){assert(x>=0&&x<W&&y>=0&&y<H);assert(!cells.has(x+','+y),'overlap '+x+','+y);let b={id,x,y};blocks.push(b);cells.set(x+','+y,b);}function line(id,a,z,y){for(let x=a;x<=z;x++)put(id,x,y);}
// Shared physical rules, newly laid out geometry: three descending bridges.
for(let x=0;x<W;x++)if(x!==61)put(52,x,7);line(52,14,W-1,15);
line(123,1,W-1,19);line(4,1,12,18);line(6,13,W-1,18);
for(let y=8;y<19;y++)put(62,0,y);line(62,1,12,8);line(62,1,12,13);
for(let i=0;i<10;i++)put(100+i,1+i,6);
// Failure under any bridge goes into the leftward spring and water return lane.
const sections=[{a:14,z:54,y:8,period:8},{a:65,z:122,y:11,period:10},{a:133,z:200,y:14,period:12}];
for(let s=0;s<sections.length;s++){let q=sections[s];for(let x=q.a;x<=q.z;x++){let phase=(x-q.a)%q.period; // Predictable green disappearing runs, amber rest islands.
 if(s===0){if(phase<3)put(62,x,q.y);else if(phase<7)put(124,x,q.y);}
 if(s===1){if(phase<3)put(62,x,q.y);else if(phase!==7)put(124,x,q.y);}
 if(s===2){if(phase<3)put(62,x,q.y);else if(phase!==6&&phase!==10)put(124,x,q.y);}
}}
// A tall wall stops the upper path; stepping on the green gate opens a drop onto a wide landing.
for(let gate of [{a:55,z:60,wall:61,upper:8,lower:11},{a:123,z:128,wall:129,upper:11,lower:14}]){
 line(124,gate.a,gate.z,gate.upper);for(let y=gate.upper-3;y<=gate.upper;y++)put(62,gate.wall,y);
 line(62,gate.a,gate.wall+3,gate.lower);
}
line(62,201,215,14);line(62,208,215,13);put(142,212,12);put(73,208,12);put(75,215,12);
// Clear route labels above each section, made from the same structural block.
const font={'D':['110','101','101','101','110'],'R':['110','101','110','101','101'],'O':['111','101','101','101','111'],'P':['110','101','110','100','100'],'1':['010','110','010','010','111'],'2':['110','001','010','100','111'],'3':['110','001','010','001','110']};
// Above the magnet there is not enough space for letters: mark each start with one/two/three amber pips.
for(let s=0;s<3;s++)for(let i=0;i<=s;i++)put(62,sections[s].a+i*2,1);
const src=fs.readFileSync('다리건너기1.LMF'),header=Buffer.from(src.subarray(0,32));header.writeUInt16LE(W,16);header.writeUInt16LE(H,18);header.writeUInt32LE(blocks.length,21);
let out=Buffer.alloc(32+blocks.length*8);header.copy(out);blocks.forEach((b,i)=>{let p=32+i*8;out.writeUInt32LE(b.id,p);out.writeInt16LE(b.x,p+4);out.writeInt16LE(b.y,p+6);});fs.writeFileSync('다리건너기3.LMF',out);
let d=fs.readFileSync('다리건너기3.LMF');assert.equal(d.length,32+d.readUInt32LE(21)*8);for(let i=0;i<blocks.length;i++){let p=32+i*8,b=blocks[i];assert.equal(d.readUInt32LE(p),b.id);assert.equal(d.readInt16LE(p+4),b.x);assert.equal(d.readInt16LE(p+6),b.y);}
assert.equal(cells.size,blocks.length);for(let q of sections){let p=blocks.filter(b=>b.y===q.y&&b.x>=q.a&&b.x<=q.z).sort((a,b)=>a.x-b.x);for(let i=1;i<p.length;i++)assert(p[i].x-p[i-1].x<=2);}
let counts={};for(let b of blocks)counts[b.id]=(counts[b.id]||0)+1;fs.writeFileSync('analysis/bridge3_maps.json',JSON.stringify([{name:'다리건너기3.LMF',width:W,height:H,count:blocks.length,counts,blocks}]));
fs.writeFileSync('analysis/bridge3_notes.txt','다리건너기3 - 내려가는 다리\n216 x 20 / 일반 갈색 발판 + 초록 사라지는 발판\n첫 구간: 사라지는 발판 학습. 둘째: 한 칸 공백. 셋째: 긴 연속 발판.\n두 전환 구간은 앞의 벽 때문에 초록 발판이 사라질 때 아래 넓은 착지대로 내려가 진행합니다.\n블록 소멸 시간 및 실제 캐릭터 충돌/자석 범위/복귀 동작은 인게임 확인 필요.\n원본 맵 수정 없음.\n');console.log({bytes:d.length,blocks:blocks.length,counts,validation:'binary roundtrip, bounds, unique coordinates, route gaps <= 2 cells: PASS'});

