Add-Type -AssemblyName System.Drawing
$maps=Get-Content analysis/bridge7_maps.json -Raw | ConvertFrom-Json
$tm=Get-Content analysis/tilemap.json -Raw | ConvertFrom-Json
$cache=@{}
foreach($p in $tm.PSObject.Properties){$path=Join-Path $pwd ('analysis/bitmap_'+$p.Value+'.bmp');if(Test-Path $path){$im=[System.Drawing.Bitmap]::FromFile($path);$im.MakeTransparent([System.Drawing.Color]::Magenta);$cache[[string]$p.Name]=$im}}
$font=New-Object System.Drawing.Font 'Arial',11
for($mi=0;$mi -lt $maps.Count;$mi++){
$m=$maps[$mi];$sheet=New-Object System.Drawing.Bitmap 1600,1800;$g=[System.Drawing.Graphics]::FromImage($sheet);$g.Clear([System.Drawing.Color]::FromArgb(26,33,48))
for($seg=0;$seg -lt 5;$seg++){$g.DrawString(($m.name+' | x='+($seg*100)+'..'+($seg*100+99)),$font,[System.Drawing.Brushes]::White,0,[single]($seg*360));foreach($b in $m.blocks){if($b.x -ge $seg*100 -and $b.x -lt ($seg+1)*100){$x=($b.x-$seg*100)*16;$y=$seg*360+24+$b.y*16;$im=$cache[[string]$b.id];if($im){$g.DrawImage($im,[int]$x,[int]$y,16,16)}else{$g.FillRectangle([System.Drawing.Brushes]::OrangeRed,$x,$y,16,16)}}}}
$sheet.Save((Join-Path $pwd ('analysis/bridge7_map_'+$mi+'.png')),[System.Drawing.Imaging.ImageFormat]::Png);$g.Dispose();$sheet.Dispose()
}
$ids=@($maps | ForEach-Object {$_.counts.PSObject.Properties.Name}) | Sort-Object {[int]$_} -Unique
$sheet=New-Object System.Drawing.Bitmap 960,([int][Math]::Ceiling($ids.Count/8)*105);$g=[System.Drawing.Graphics]::FromImage($sheet);$g.Clear([System.Drawing.Color]::LightGray)
for($i=0;$i -lt $ids.Count;$i++){$id=$ids[$i];$x=($i%8)*120;$y=[Math]::Floor($i/8)*105;$im=$cache[$id];if($im){$g.DrawImage($im,[int]$x,[int]$y,48,48)};$g.DrawString(('ID '+$id),$font,[System.Drawing.Brushes]::Black,[single]$x,[single]($y+55))}
$sheet.Save((Join-Path $pwd 'analysis/bridge7_used_tiles.png'),[System.Drawing.Imaging.ImageFormat]::Png);$g.Dispose();$sheet.Dispose();foreach($im in $cache.Values){$im.Dispose()}

