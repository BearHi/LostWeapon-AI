const fs=require('fs');const W=50,H=50,S=14;const a=Array.from({length:H},()=>Array(W).fill(0));
const put=(x,y,v)=>{if(x>=0&&x<W&&y>=0&&y<H)a[y][x]=v};const rect=(x,y,w,h,v)=>{for(let j=0;j<h;j++)for(let i=0;i<w;i++)put(x+i,y+j,v)};
// irregular map walls, leaving a winding playable air route
rect(0,0,50,2,1);rect(0,48,50,2,1);rect(0,0,2,50,1);rect(48,0,2,50,1);
for(const q of [[3,3,12,8],[20,3,13,5],[36,3,10,10],[4,15,8,13],[16,12,11,8],[30,13,14,11],[40,25,7,13],[4,31,13,10],[21,27,12,12],[34,36,13,10],[5,44,15,3],[27,44,15,3]])rect(...q,1);
// lava sheets and cracks
for(const q of [[15,5,4,12],[27,8,3,14],[9,24,11,3],[25,21,13,3],[36,30,4,13],[16,38,4,10],[42,41,5,6]])rect(...q,2);
// safe stone ledges
for(const q of [[3,12,10,2],[13,19,10,2],[25,25,9,2],[34,33,10,2],[24,40,11,2],[7,42,10,2]])rect(...q,3);
// spikes
for(const [x,y] of [[11,11],[22,18],[32,24],[43,32],[20,39],[38,42]])put(x,y,4);
let svg='<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700" viewBox="0 0 700 700" shape-rendering="crispEdges"><rect width="700" height="700" fill="#fff"/>';
for(let y=0;y<H;y++)for(let x=0;x<W;x++){let v=a[y][x];if(!v)continue;let c=v===1?'#111':v===2?'#e33b20':v===3?'#d7c38d':'#fff';svg+='<rect x="'+x*S+'" y="'+y*S+'" width="'+S+'" height="'+S+'" fill="'+c+'"/>'}
for(let x=0;x<=W;x++)svg+='<path d="M'+x*S+' 0V'+H*S+'" stroke="#b8c3d2" stroke-width="1"/>';for(let y=0;y<=H;y++)svg+='<path d="M0 '+y*S+'H'+W*S+'" stroke="#b8c3d2" stroke-width="1"/>';svg+='<rect x="42" y="574" width="14" height="14" fill="#44c7e8"/><rect x="644" y="42" width="14" height="14" fill="#f5c542"/></svg>';fs.writeFileSync('analysis/도트_용암맵_50x50.svg',svg);
