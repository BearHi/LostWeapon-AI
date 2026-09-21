const fs=require('fs');const W=100,H=100,S=8;let a=Array.from({length:H},()=>Array(W).fill(0));
const rect=(v,x1,y1,x2,y2)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)a[y][x]=v};
// irregular stepped rock masses
for(const q of [[0,0,32,14],[39,0,69,10],[76,0,99,18],[0,24,18,48],[28,19,47,34],[55,17,73,39],[83,25,99,52],[0,59,25,80],[34,48,52,69],[61,55,78,77],[86,63,99,91],[6,86,36,99],[49,85,69,99]])rect(1,...q);
// carve large chambers
for(const q of [[4,6,25,18],[43,5,63,20],[79,6,94,25],[8,29,28,46],[35,23,53,42],[63,24,82,46],[22,56,40,74],[45,54,62,72],[72,60,88,79],[12,84,31,95],[52,86,64,96]])rect(0,...q);
// lava channels and pools
for(const q of [[27,0,33,27],[70,0,75,35],[53,35,61,54],[2,49,33,55],[40,43,48,70],[79,47,86,70],[31,75,58,81],[68,80,99,86],[38,92,48,99]])rect(2,...q);
// irregular lava tongues
for(const q of [[24,14,29,19],[30,18,37,22],[63,11,70,17],[74,27,82,32],[17,47,24,53],[58,45,66,51],[86,50,93,58],[27,70,34,77]])rect(2,...q);
// safe light rock islands / route stepping stones
for(const q of [[6,20,16,22],[21,30,31,32],[38,21,46,23],[50,29,57,31],[64,48,73,50],[27,57,36,59],[49,73,58,75],[68,51,77,53],[83,73,91,75],[32,83,42,85],[61,81,69,83]])rect(3,...q);
// stairs and narrow connectors
for(const q of [[16,21,20,23],[31,31,36,33],[57,30,63,32],[73,49,79,51],[36,58,42,60],[58,74,65,76],[77,52,83,54],[42,84,50,86]])rect(3,...q);
// route hint cells
const path=[[8,21],[18,21],[25,31],[42,22],[54,30],[68,49],[32,58],[53,74],[86,74],[64,82],[37,84]];
let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 800 800"><rect width="800" height="800" fill="#161b28"/>`;
for(let y=0;y<H;y++)for(let x=0;x<W;x++){let v=a[y][x];if(!v)continue;let col=v===1?'#704522':v===2?'#f04b22':'#d8c48a';svg+=`<rect x="${x*S}" y="${y*S}" width="${S}" height="${S}" fill="${col}"/>`;}
for(const [x,y] of path)svg+=`<circle cx="${x*S+4}" cy="${y*S+4}" r="2.4" fill="#63e6ff"/>`;
svg+=`<text x="12" y="18" fill="#fff" font-size="12">HELL CONCEPT / cyan = intended route, pale = rest islands</text></svg>`;fs.writeFileSync('analysis/지옥_도트설계도.svg',svg);console.log('written')
