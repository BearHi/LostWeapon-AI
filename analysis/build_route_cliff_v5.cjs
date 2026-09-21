const fs=require('fs');const W=25,H=180,m=new Map();
const put=(id,x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)m.set(`${x},${y}`,{id,x,y});};
const fill=(id,a,b,y)=>{for(let x=a;x<=b;x++)put(id,x,y);};
// Organic outer walls; the center remains a chain of large rooms.
for(let y=0;y<H;y++){let l=2+Math.floor(1.5+1.7*Math.sin(y*.11)),r=2+Math.floor(1.5+1.7*Math.cos(y*.085));for(let x=0;x<l;x++)put(8,x,y);for(let x=W-r;x<W;x++)put(8,x,y);}
// Route anchors: alternating ledges with enough open space for a movement, not stairs.
const route=[
 [3,171,7,'L'],[15,158,5,'R'],[6,145,5,'L'],[16,132,5,'R'],
 [8,119,4,'L'],[18,106,4,'R'],[6,93,5,'L'],[15,80,5,'R'],
 [8,67,4,'L'],[17,54,5,'R'],[5,41,5,'L'],[14,28,5,'R'],[7,15,8,'L']
];
for(const [x,y,w,s] of route){for(let k=0;k<3;k++){let tip=s==='L'?x+w-1-k:x+k;for(let xx=s==='L'?0:tip; s==='L'?xx<=tip:xx<W;xx++)put(8,xx,y+k);}}
// Each device changes how the next anchor is reached.
put(4,10,159);for(let d=1;d<=4;d++)m.delete(`10,${159-d}`); // spring to right ledge
for(let x=16;x<=20;x++)put(19,x,132); // slippery right landing
put(122,8,119);put(122,9,119);for(let x=8;x<=9;x++)for(let d=1;d<=3;d++)m.delete(`${x},${119+d}`);
put(51,12,106);put(51,13,106); // fan in the lower edge of next room
put(119,20,93);put(119,4,41); // timing hazards on outside edges
put(86,22,145);put(86,2,80);put(86,22,28);
put(118,21,67);put(118,3,15); // upward lava jets force side switching
fill(8,0,W-1,H-1);put(100,4,171);
const src=fs.readFileSync('학습용/암벽.LMF'),a=[...m.values()],b=Buffer.alloc(32+a.length*8);src.copy(b,0,0,32);b.writeUInt16LE(W,16);b.writeUInt16LE(H,18);b.writeUInt32LE(a.length,21);a.forEach((r,i)=>{let p=32+i*8;b.writeUInt32LE(r.id,p);b.writeInt16LE(r.x,p+4);b.writeInt16LE(r.y,p+6)});fs.writeFileSync('암벽_연결루트_v5.LMF',b);fs.writeFileSync('analysis/cliff_v5.json',JSON.stringify({w:W,h:H,route,records:a}));console.log(`${W}x${H}, ${a.length} blocks`);
