const fs=require('fs');
const W=25,H=240,c=new Map();
function put(id,x,y){if(x<0||x>=W||y<0||y>=H)throw Error('bounds');c.set(x+','+y,{id,x,y});}
// Contiguous asymmetric cliff silhouettes, without stippling or repeated holes.
for(let y=0;y<H;y++){
 let l=2+Math.round(1.1*Math.sin(y*.091)+.7*Math.sin(y*.21));
 let r=2+Math.round(1.2*Math.sin(y*.073+2)+.6*Math.sin(y*.17));
 for(let x=0;x<=l;x++)put(8,x,y);
 for(let x=W-1-r;x<W;x++)put(8,x,y);
}
for(let x=0;x<W;x++)for(let y=236;y<H;y++)put(8,x,y);
// Short rising stone steps: each next landing is one cell higher,
// with two-cell horizontal advance. Turns form broader resting ledges.
let y=235,x=5,dir=1,stage=0;const route=[];
while(y>10){
 route.push({x,y});
 for(let k=0;k<3;k++){let xx=x+k;if(xx>=4&&xx<=20)put(8,xx,y);}
 // A tapered underside gives each ledge a rock silhouette.
 if(stage%3===0&&y+1<236)put(8,x+1,y+1);
 const stride=[2,3,2,2,3][route.length%5]; const nx=x+dir*stride;
 if(nx>17||nx<5){dir=-dir;stage++;}
 else x=nx;
 y-= [2,2,3,2,3,2,2][route.length%7];
}
// Keep the travel space clear of side-wall bulges.
for(const p of route)for(let yy=p.y-3;yy<p.y;yy++)for(let xx=p.x;xx<p.x+3;xx++){
 if(xx>=4&&xx<=20&&yy>=0){const k=xx+','+yy;const v=c.get(k);if(v&& (xx<5||xx>19))c.delete(k);}
}
// Wide start and summit, one spawn only.
for(let xx=4;xx<21;xx++)put(8,xx,8);
put(100,7,232);
const records=[...c.values()];const src=fs.readFileSync('학습용/암벽.LMF');
const out=Buffer.alloc(32+records.length*8);src.copy(out,0,0,32);out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(records.length,21);
records.forEach((r,i)=>{let o=32+i*8;out.writeUInt32LE(r.id,o);out.writeInt16LE(r.x,o+4);out.writeInt16LE(r.y,o+6)});
fs.writeFileSync('암벽_돌능선_v1.LMF',out);
fs.writeFileSync('analysis/cliff_new.json',JSON.stringify({w:W,h:H,records}));
if(out.length!==32+out.readUInt32LE(21)*8||records.filter(r=>r.id===100).length!==1)throw Error('validation');
console.log(W,H,records.length);

