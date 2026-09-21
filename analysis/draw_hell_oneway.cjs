const fs=require('fs');const W=100,H=100,S=8;let a=Array.from({length:H},()=>Array(W).fill(0));const rect=(v,x1,y1,x2,y2)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)a[y][x]=v};const blob=(v,cx,cy,rx,ry)=>{for(let y=cy-ry;y<=cy+ry;y++)for(let x=cx-rx;x<=cx+rx;x++)if(((x-cx)/(rx||1))**2+((y-cy)/(ry||1))**2<1)a[y][x]=v};
// large organic rock masses
for(const q of [[0,0,28,18],[38,0,67,13],[78,0,99,24],[0,29,16,57],[25,23,45,43],[55,22,75,44],[84,33,99,62],[0,66,24,99],[34,60,55,80],[63,66,82,99],[89,73,99,99]])rect(1,...q);
// chambers
for(const q of [[5,7,23,22],[43,6,61,24],[80,7,95,29],[5,36,25,56],[31,28,49,48],[58,29,76,51],[72,43,92,65],[8,74,28,94],[39,65,58,84],[67,75,85,95]])rect(0,...q);
// lava basins and roll crossings
for(const q of [[25,17,36,21],[61,14,77,18],[18,56,35,61],[48,48,64,53],[76,65,90,70],[28,83,43,88],[56,86,70,91]])rect(2,...q);
// pale safe islands
for(const q of [[7,88,17,90],[19,77,29,79],[27,63,39,65],[38,52,48,54],[49,41,59,43],[57,31,67,33],[67,20,78,22],[79,9,91,11]])rect(3,...q);
// monotonic route, start bottom-left -> finish top-right
const p=[[10,88],[24,78],[33,64],[43,53],[53,42],[62,32],[72,21],[85,10]];let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 800 800"><rect width="800" height="800" fill="#141a27"/>`;
for(let y=0;y<H;y++)for(let x=0;x<W;x++){let v=a[y][x];if(v){let col=v===1?'#754722':v===2?'#f04b22':'#d8c48a';svg+=`<rect x="${x*S}" y="${y*S}" width="${S}" height="${S}" fill="${col}"/>`;}}
let pp=p.map(([x,y])=>`${x*S+4},${y*S+4}`).join(' ');svg+=`<polyline points="${pp}" fill="none" stroke="#36d9ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;p.forEach(([x,y],i)=>{svg+=`<circle cx="${x*S+4}" cy="${y*S+4}" r="6" fill="#172032" stroke="#fff"/><text x="${x*S+1}" y="${y*S+2}" fill="#fff" font-size="7">${i+1}</text>`});for(const [x,y] of [[24,78],[43,53],[72,21]])svg+=`<text x="${x*S-10}" y="${y*S-5}" fill="#ffd35a" font-size="9">ROLL</text>`;svg+=`<text x="18" y="780" fill="#fff" font-size="14">START 1 → 8 → FINISH</text></svg>`;fs.writeFileSync('analysis/지옥_화산도트_단방향.svg',svg)
