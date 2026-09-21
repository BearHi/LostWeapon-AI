const fs=require('fs');
const W=33,H=220,m=new Map();
const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)m.set(`${x},${y}`,{id,x,y});};
const fill=(id,x1,x2,y1,y2)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)put(id,x,y);};
// New topology: two uneven walls, three wide chambers, and offset recovery shelves.
for(let y=0;y<H;y++){
  const l=2+Math.floor(2*Math.sin(y*.17)+1.5), r=2+Math.floor(2*Math.cos(y*.13+1));
  fill(8,0,l-1,y,y); fill(8,W-r,W-1,y,y);
}
const ledges=[
 [3,210,8,'L'],[5,202,4,'L'],[8,194,4,'L'],[12,185,5,'R'],[16,176,4,'R'],
 [20,166,5,'R'],[17,156,3,'L'],[13,147,5,'L'],[8,137,4,'L'],[11,127,4,'R'],
 [16,118,5,'R'],[21,108,4,'R'],[18,97,4,'L'],[13,87,5,'L'],[8,77,4,'L'],
 [11,67,4,'R'],[16,57,5,'R'],[21,47,4,'R'],[18,37,3,'L'],[13,27,5,'L'],[8,17,5,'L'],[5,8,8,'R']
];
for(const [x,y,w,s] of ledges){for(let k=0;k<3;k++){const tip=s==='L'?x+w-1-k:x+k;for(let xx=s==='L'?0:tip; s==='L'?xx<=tip:xx<W; xx+=s==='L'?1:1)put(8,xx,y+k);}}
// Distinct mechanics: launch transfer, slippery landing, timed lips, fan ascent, hazards.
for(const [x,y] of [[10,186],[14,128],[10,68],[15,28]]){put(4,x,y);for(let d=1;d<=4;d++)m.delete(`${x},${y-d}`);}
for(let x=20;x<=24;x++)put(19,x,166); for(let x=13;x<=17;x++)put(19,x,87);
for(const [x,y] of [[8,137],[9,137],[18,97],[19,97]]){put(122,x,y);for(let d=1;d<=3;d++)m.delete(`${x},${y+d}`);}
put(51,22,112);put(51,23,112);put(51,24,112);
for(const [x,y] of [[2,154],[29,119],[3,46],[28,18]])put(119,x,y);
for(const [x,y] of [[28,171],[3,132],[29,61],[4,22]])put(86,x,y);
for(const [x,y] of [[26,180],[4,101],[27,70]])put(118,x,y);
fill(8,0,W-1,H-1,H-1);put(100,5,209);
const src=fs.readFileSync('학습용/암벽.LMF'),a=[...m.values()],out=Buffer.alloc(32+a.length*8);src.copy(out,0,0,32);out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(a.length,21);a.forEach((r,i)=>{const p=32+i*8;out.writeUInt32LE(r.id,p);out.writeInt16LE(r.x,p+4);out.writeInt16LE(r.y,p+6)});fs.writeFileSync('암벽_용암균열_v4.LMF',out);fs.writeFileSync('analysis/cliff_v4.json',JSON.stringify({w:W,h:H,records:a}));console.log(`${W}x${H}, ${a.length} blocks`);
