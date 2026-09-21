Add-Type -AssemblyName System.Drawing
$d=Get-Content (Join-Path $PSScriptRoot 'user_cliff_diff.json') -Raw|ConvertFrom-Json
$b=[Drawing.Bitmap]::new(930,710);$g=[Drawing.Graphics]::FromImage($b);$g.Clear([Drawing.Color]::FromArgb(21,26,31))
$font=[Drawing.Font]::new('Arial',12)
$zones=@(@{x=0;y=30;w=16;h=22;label='A: left wall / y30-51'},@{x=16;y=54;w=15;h=23;label='B: right wall / y54-76'})
for($z=0;$z -lt 2;$z++){
 $q=$zones[$z];$oy=35+$z*340;$s=13
 for($panel=0;$panel -lt 3;$panel++){
  $ox=15+$panel*310;$label=@('BEFORE','AFTER','CHANGES: green + / red -')[$panel]
  $g.DrawString($q.label+'  '+$label,$font,[Drawing.Brushes]::White,$ox,$oy-25)
  $recs=$d.before.records;if($panel -eq 1){$recs=$d.after.records}
  foreach($r in $recs){if($r.x -lt $q.x -or $r.x -ge $q.x+$q.w -or $r.y -lt $q.y -or $r.y -ge $q.y+$q.h){continue};$g.FillRectangle([Drawing.Brushes]::Sienna,($ox+($r.x-$q.x)*$s),($oy+($r.y-$q.y)*$s),$s-1,$s-1)}
  if($panel -eq 2){foreach($r in $d.removed){if($r.x -ge $q.x -and $r.x -lt $q.x+$q.w -and $r.y -ge $q.y -and $r.y -lt $q.y+$q.h){$g.FillRectangle([Drawing.Brushes]::Red,($ox+($r.x-$q.x)*$s),($oy+($r.y-$q.y)*$s),$s-1,$s-1)}};foreach($r in $d.added){if($r.x -ge $q.x -and $r.x -lt $q.x+$q.w -and $r.y -ge $q.y -and $r.y -lt $q.y+$q.h){$g.FillRectangle([Drawing.Brushes]::LimeGreen,($ox+($r.x-$q.x)*$s),($oy+($r.y-$q.y)*$s),$s-1,$s-1)}}}
 }
}
$b.Save((Join-Path $PSScriptRoot '암벽수정_전후비교.png'));$g.Dispose();$b.Dispose();$font.Dispose()
