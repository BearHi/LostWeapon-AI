const fs=require('fs');const W=25,H=130,m=new Map();const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)m.set(`${x},${y}`,{id,x,y});};
// Thick, uneven cave walls with changing chamber widths.
for(let y=0;y<H;y++){const l=2+Math.floor(2*Math.sin(y*.19)+1.5),r=2+Math.floor(2*Math.cos(y*.15+1)+1.5);for(let x=0;x<l;x++)put(8,x,y);for(let x=W-r;x<W;x++)put(8,x,y);}
// The route uses short wall ledges; horizontal travel stays near 4-5 cells.
const p=[[3,121,7,'L'],[8,116,4,'L'],[12,112,4,'R'],[16,107,4,'R'],[12,103,3,'R'],[8,99,4,'L'],[5,94,4,'L'],[10,90,4,'L'],[14,85,4,'R'],[18,80,4,'R'],[14,76,3,'R'],[10,72,4,'L'],[6,68,4,'L'],[9,63,4,'L'],[13,59,4,'R'],[17,54,4,'R'],[13,50,3,'R'],[9,46,4,'L'],[5,42,4,'L'],[8,37,4,'L'],[12,33,4,'R'],[16,28,4,'R'],[12,24,3,'R'],[8,20,4,'L'],[5,16,5,'L'],[8,11,5,'L'],[6,6,7,'L']];
for(const [x,y,w,s] of p){const tip=s==='L'?x+w-1:x;for(let xx=s==='L'?0:tip;s==='L'?xx<=tip:xx<W;xx++)put(8,xx,y);if(s==='L')put(8,tip,y+1);else put(8,tip,y+1);}
// Only route-relevant mechanics.
put(4,10,108);for(let d=1;d<=4;d++)m.delete(`10,${108-d}`);
for(let x=14;x<=17;x++)put(19,x,85);put(122,9,63);put(122,10,63);for(let x=9;x<=10;x++)for(let d=1;d<=3;d++)m.delete(`${x},${63+d}`);put(51,13,54);put(119,21,42);put(86,3,37);put(118,20,24);
for(let x=0;x<W;x++)put(8,x,H-1);put(100,4,121);
const src=fs.readFileSync('학습용/암벽.LMF'),a=[...m.values()],b=Buffer.alloc(32+a.length*8);src.copy(b,0,0,32);b.writeUInt16LE(W,16);b.writeUInt16LE(H,18);b.writeUInt32LE(a.length,21);a.forEach((r,i)=>{let q=32+i*8;b.writeUInt32LE(r.id,q);b.writeInt16LE(r.x,q+4);b.writeInt16LE(r.y,q+6)});fs.writeFileSync('암벽_낭떠러지_v10.LMF',b);fs.writeFileSync('analysis/cliff_v10.json',JSON.stringify({w:W,h:H,records:a}));console.log(`${W}x${H}, ${a.length} blocks`);
