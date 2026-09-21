const fs=require('fs');const W=100,H=100,S=7,seed=17;let g=Array.from({length:H},()=>Array(W).fill(1));function rnd(x,y){let n=Math.sin(x*12.9898+y*78.233+seed)*43758.5453;return n-Math.floor(n)}function smooth(x,y){let v=rnd(x,y)+rnd(x+1,y)+rnd(x,y+1)+rnd(x+1,y+1);return v/4}
// dense lava field with cellular irregularity
for(let y=3;y<H-3;y++)for(let x=3;x<W-3;x++){let n=smooth(Math.floor(x/3),Math.floor(y/3));g[y][x]=n>.47?2:1}
// carve large connected air pockets, uneven stepped boundaries
const carve=(x,y,w,h)=>{for(let j=0;j<h;j++)for(let i=0;i<w;i++){let xx=x+i,yy=y+j;if(xx>=0&&xx<W&&yy>=0&&yy<H&&((i*7+j*11+seed)%13>2))g[yy][xx]=0}}
for(const q of [[8,11,19,15],[34,9,18,16],[61,12,24,20],[15,34,22,18],[45,31,18,23],[75,38,18,21],[6,61,20,18],[31,58,22,21],[61,65,22,18],[17,83,25,13],[53,84,20,12],[77,77,16,15]])carve(...q)
// rock veins / borders in 1-3 cell widths
const vein=(x,y,pts)=>{for(const [dx,dy,w] of pts){for(let j=0;j<w;j++)for(let i=0;i<w;i++)if(rnd(x+dx+i,y+dy+j)>.18)g[y+dy+j][x+dx+i]=3}}
vein(0,0,[[6,10,2],[18,22,2],[28,35,3],[42,27,2],[55,40,2],[68,28,3],[78,47,2],[62,60,2],[45,73,3],[27,67,2],[12,81,2]])
// force outer rocky frame with lava gaps
for(let x=0;x<W;x++){g[0][x]=3;g[1][x]=3;g[H-1][x]=3;g[H-2][x]=3}for(let y=0;y<H;y++){g[y][0]=3;g[y][1]=3;g[y][W-1]=3;g[y][W-2]=3}
let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700" viewBox="0 0 700 700" shape-rendering="crispEdges"><rect width="700" height="700" fill="#141923"/>`;
for(let y=0;y<H;y++)for(let x=0;x<W;x++){let v=g[y][x];if(!v)continue;let c=v===1?'#8b5429':v===2?'#e84b21':'#a7a9a6';svg+=`<rect x="${x*S}" y="${y*S}" width="${S}" height="${S}" fill="${c}"/>`;}
svg+=`</svg>`;fs.writeFileSync('analysis/지옥_도트밀도_시안.svg',svg)
