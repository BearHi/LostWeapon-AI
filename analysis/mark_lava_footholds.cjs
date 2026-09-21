const fs = require('fs');
const d = fs.readFileSync('영상/용암.LMF');
const W = d.readUInt16LE(16), H = d.readUInt16LE(18), S = 8;
const a = new Map();
for (let o = 32; o < d.length; o += 8) {
  const id = d.readUInt32LE(o), x = d.readInt16LE(o + 4), y = d.readInt16LE(o + 6);
  a.set(x + ',' + y, id);
}
const isFloor = id => id === 7 || (id >= 110 && id <= 117);
let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800" shape-rendering="crispEdges"><rect width="800" height="800" fill="#151a25"/>';
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const id = a.get(x + ',' + y); if (id === undefined) continue;
  const col = id === 49 ? '#f04a22' : isFloor(id) ? '#d8c487' : id === 86 ? '#f2f2ed' : '#744720';
  svg += '<rect x="'+x*S+'" y="'+y*S+'" width="'+S+'" height="'+S+'" fill="'+col+'"/>';
}
// highlight every actual foothold tile; no path is drawn through brown terrain
for (const [key,id] of a) if (isFloor(id)) {
  const [x,y] = key.split(',').map(Number);
  svg += '<rect x="'+(x*S+1)+'" y="'+(y*S+1)+'" width="'+(S-2)+'" height="'+(S-2)+'" fill="none" stroke="#35e6ff" stroke-width="1"/>';
}
const sx=13, sy=87;
svg += '<circle cx="'+(sx*S+4)+'" cy="'+(sy*S+4)+'" r="5" fill="#ff3b63" stroke="#fff"/><text x="'+(sx*S+8)+'" y="'+(sy*S)+'" fill="#fff" font-size="12">START ID100</text>';
svg += '<text x="12" y="792" fill="#fff" font-size="12">cyan outline = actual pale foothold / brown is never used as a route line</text></svg>';
fs.writeFileSync('analysis/용암_실제발판표시.svg', svg);
