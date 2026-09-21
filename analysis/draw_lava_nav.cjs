const fs = require('fs');
const d = fs.readFileSync('영상/용암.LMF');
const W = d.readUInt16LE(16), H = d.readUInt16LE(18), S = 8;
const a = new Map();
for (let o = 32; o < d.length; o += 8) {
  const id = d.readUInt32LE(o), x = d.readInt16LE(o + 4), y = d.readInt16LE(o + 6);
  a.set(x + ',' + y, id);
}
let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800" shape-rendering="crispEdges"><rect width="800" height="800" fill="#151a25"/>';
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const id = a.get(x + ',' + y); if (id === undefined) continue;
  const col = id === 49 ? '#f04a22' : (id === 7 || (id >= 110 && id <= 117)) ? '#d4bf84' : id === 86 ? '#f2f2ed' : '#744720';
  svg += '<rect x="' + x*S + '" y="' + y*S + '" width="' + S + '" height="' + S + '" fill="' + col + '"/>';
}
const p = [[13,87],[24,92],[34,84],[43,75],[52,66],[61,56],[69,47],[76,38],[85,29],[93,19],[96,8]];
svg += '<polyline points="' + p.map(q => (q[0]*S+4)+','+(q[1]*S+4)).join(' ') + '" fill="none" stroke="#38e1ff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>';
p.forEach((q,i) => { svg += '<circle cx="'+(q[0]*S+4)+'" cy="'+(q[1]*S+4)+'" r="5" fill="#182338" stroke="#fff"/><text x="'+(q[0]*S+1)+'" y="'+(q[1]*S+2)+'" fill="#fff" font-size="7">'+(i+1)+'</text>'; });
svg += '<text x="10" y="792" fill="#fff" font-size="12">cyan = hypothesized navigation / start ID100 at 13,87</text></svg>';
fs.writeFileSync('analysis/용암_네비게이션_가설.svg', svg);
