const fs=require('fs');const W=25,H=210,m=new Map();
function put(id,x,y){if(x<0||x>=W||y<0||y>=H)throw Error('bounds');m.set(`${x},${y}`,{id,x,y});}
const left=[[0,5],[12,3],[24,4],[35,1],[47,3],[60,2],[72,5],[85,2],[101,1],[118,4],[130,2],[147,5],[160,2],[180,1],[193,3],[209,3]];
const right=[[0,3],[18,2],[31,5],[45,2],[61,1],[79,3],[93,5],[106,2],[125,1],[141,3],[153,2],[171,4],[189,2],[209,3]];
function edge(points,y){let i=0;while(i<points.length-2&&points[i+1][0]<y)i++;const [a,v]=points[i],[b,w]=points[i+1];return Math.round(v+(w-v)*(y-a)/(b-a));}
for(let y=0;y<H;y++){for(let x=0;x<edge(left,y);x++)put(8,x,y);for(let x=W-edge(right,y);x<W;x++)put(8,x,y);}
// Each manually placed outcrop is tied to one cliff, tapered downwards.
function ledge(x,y,w,side,depth=4){for(let k=0;k<depth;k++){
 const tip=side==='L'?x+w-1-Math.floor(k*.9):x+Math.floor(k*.9);
 if(side==='L'){for(let xx=0;xx<=tip;xx++)put(8,xx,y+k);}else{for(let xx=tip;xx<W;xx++)put(8,xx,y+k);}
}return {x,y,w,side};}
// Broad starting shelf, then left-face holds, a spring transfer,
// slippery right lip, a retracting-spike traverse, and the summit face.
const landings=[
 [3,202,7,'L',5],[5,197,3,'L',3],[7,192,2,'L',3],
 [6,187,3,'L',4],[9,182,2,'L',3],[14,176,4,'R',6],
 [17,170,3,'R',3],[15,165,2,'R',4],[12,160,3,'R',4],
 [7,154,4,'L',7],[5,149,3,'L',3],[8,143,2,'L',4],
 [11,138,2,'L',3],[16,131,4,'R',7],[18,125,2,'R',3],
 [15,119,3,'R',4],[12,114,3,'R',4],[7,108,4,'L',6],
 [4,102,3,'L',3],[7,97,2,'L',4],[9,91,3,'L',5],
 [15,83,4,'R',7],[18,77,2,'R',4],[16,71,2,'R',3],
 [12,65,3,'R',5],[7,59,4,'L',7],[5,53,3,'L',4],
 [8,47,2,'L',4],[10,41,3,'L',4],[16,33,4,'R',6],
 [18,27,2,'R',4],[15,21,3,'R',4],[10,15,3,'L',4],
 [5,8,9,'L',5]
];landings.forEach(q=>ledge(...q));
// Place mechanisms on top surfaces, not inside their supporting rock.
for(const [x,y] of [[10,181],[11,137],[10,90],[11,40]])put(4,x,y);
// Ice shelf at the right face: clear of landing edge; same collision footprint.
for(let x=17;x<=21;x++)put(19,x,170);
for(let x=15;x<=20;x++)put(19,x,119);
// Disappearing lips used as short standing surfaces.
put(122,8,143);put(122,9,143);put(122,16,71);put(122,17,71);
for(const [x,y] of [[8,143],[9,143],[16,71],[17,71]])for(let d=1;d<=4;d++)m.delete(`${x},${y+d}`);
// Timing hazards occupy outer portions, leaving inner landing space.
put(119,20,130);put(119,4,107);put(119,20,32);
// Small fixed spikes punish hugging the outside edge; avoid the takeoff tiles.
put(86,22,164);put(86,2,153);put(86,22,64);
// Local launch columns must have at least four clear cells overhead.
for(const [x,y] of [[10,181],[11,137],[10,90],[11,40]])for(let dy=1;dy<=4;dy++)m.delete(`${x},${y-dy}`);
for(let x=0;x<W;x++)put(8,x,209);
put(100,6,199);
const rec=[...m.values()],src=fs.readFileSync('학습용/암벽.LMF'),out=Buffer.alloc(32+rec.length*8);src.copy(out,0,0,32);out.writeUInt16LE(W,16);out.writeUInt16LE(H,18);out.writeUInt32LE(rec.length,21);
rec.forEach((r,i)=>{let p=32+i*8;out.writeUInt32LE(r.id,p);out.writeInt16LE(r.x,p+4);out.writeInt16LE(r.y,p+6)});
fs.writeFileSync('암벽_갈라진절벽_v2.LMF',out);fs.writeFileSync('analysis/cliff_v2.json',JSON.stringify({w:W,h:H,records:rec}));
if(rec.filter(r=>r.id===100).length!==1||out.length!==32+8*rec.length)throw Error('Invalid');
console.log(`25x210, ${rec.length} blocks; spawn 6,199. Runtime traversal untested.`);

