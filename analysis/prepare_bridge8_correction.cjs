const fs=require('fs'),assert=require('assert');
const file='다리건너기8_자력회랑.LMF',b=fs.readFileSync(file),backup='analysis/bridge8_before_correction.LMF';
if(!fs.existsSync(backup))fs.writeFileSync(backup,b);
let out=Buffer.from(b),changed={};for(let p=32;p<out.length;p+=8){let id=out.readUInt32LE(p);if(id===62||id===124){out.writeUInt32LE(0,p);changed[id]=(changed[id]||0)+1;}}
assert.equal(out.length,b.length);assert.equal(out.readUInt32LE(21),b.readUInt32LE(21));
fs.writeFileSync('analysis/bridge8_wall_revision_pending.LMF',out);
console.log({draft:'analysis/bridge8_wall_revision_pending.LMF',changed,remaining:'Magnet positioning depends on the user explanation; current playable file is not replaced.'});
