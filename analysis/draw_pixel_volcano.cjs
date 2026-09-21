const fs=require('fs');const W=60,H=45,S=12;const a=Array.from({length:H},()=>Array(W).fill(0));
const put=(x,y,v)=>{if(x>=0&&x<W&&y>=0&&y<H)a[y][x]=v};const line=(x,y,dx,dy,n,v)=>{for(let i=0;i<n;i++)put(x+dx*i,y+dy*i,v)};
// volcanic mountain silhouette
for(let y=8;y<43;y++)for(let x=3;x<57;x++){let l=28-(y-8)*.62,r=31+(y-8)*.62;if(x>=l&&x<=r)a[y][x]=1}
// cave openings and sky gaps
for(let y=14;y<25;y++)for(let x=14;x<25;x++)if((x-19)**2+(y-20)**2<40)a[y][x]=0;
for(let y=16;y<29;y++)for(let x=36;x<48;x++)if((x-42)**2+(y-22)**2<48)a[y][x]=0;
// lava cracks
line(29,9,0,1,26,2);line(30,15,1,1,14,2);line(18,28,1,0,22,2);line(39,30,-1,0,18,2);line(27,38,1,0,20,2);
// rock ledges
for(const q of [[7,31,18,2],[26,28,12,2],[43,34,13,2],[14,40,16,2],[36,41,12,2]])for(let y=q[1];y<q[1]+q[3];y++)for(let x=q[0];x<q[0]+q[2];x++)put(x,y,3);
// spikes
for(const [x,y] of [[20,30],[33,27],[48,33]])put(x,y,4);
let svg='<svg xmlns="http://www.w3.org/2000/svg" width="720" height="540" viewBox="0 0 720 540" shape-rendering="crispEdges"><rect width="720" height="540" fill="#f7f7f7"/>';
for(let y=0;y<H;y++)for(let x=0;x<W;x++){let v=a[y][x];if(!v)continue;let c=v===1?'#4a2b1b':v===2?'#f04b20':v===3?'#d4bf86':'#f2f2e8';svg+='<rect x="'+x*S+'" y="'+y*S+'" width="'+S+'" height="'+S+'" fill="'+c+'"/>'}
for(let x=0;x<=W;x++)svg+='<path d="M'+x*S+' 0V'+H*S+'" stroke="#b7c1d0" stroke-width="1"/>';for(let y=0;y<=H;y++)svg+='<path d="M0 '+y*S+'H'+W*S+'" stroke="#b7c1d0" stroke-width="1"/>';svg+='</svg>';fs.writeFileSync('analysis/도트_화산맵_예시.svg',svg);
