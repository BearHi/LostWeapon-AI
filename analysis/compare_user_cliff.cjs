const fs=require('fs');
function read(p){let b=fs.readFileSync(p),a=[];for(let i=0;i<b.readUInt32LE(21);i++){let q=32+i*8;a.push({id:b.readUInt32LE(q),x:b.readInt16LE(q+4),y:b.readInt16LE(q+6)})}return {w:b.readUInt16LE(16),h:b.readUInt16LE(18),records:a}}
const before=read('암벽_긴협곡07.LMF'),after=read('C:/Users/microsoft/Downloads/NewLostweapon/Map/암벽수정.LMF');
const key=r=>`${r.x},${r.y}`,a=new Map(before.records.map(r=>[key(r),r])),b=new Map(after.records.map(r=>[key(r),r]));
const removed=before.records.filter(r=>!b.has(key(r))),added=after.records.filter(r=>!a.has(key(r))),changed=after.records.filter(r=>a.has(key(r))&&a.get(key(r)).id!==r.id).map(r=>({before:a.get(key(r)),after:r}));
const out={before,after,removed,added,changed};fs.writeFileSync('analysis/user_cliff_diff.json',JSON.stringify(out));console.log(JSON.stringify({dimensions:[before.w,before.h,after.w,after.h],removed,added,changed},null,2));
