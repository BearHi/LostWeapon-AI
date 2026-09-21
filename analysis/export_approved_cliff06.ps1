Add-Type -AssemblyName System.Drawing
$root=Split-Path $PSScriptRoot -Parent
$source=[Drawing.Bitmap]::FromFile((Join-Path $PSScriptRoot '암벽_도트초안_06.png'))
$w=25;$h=104;$cell=12
$blocks=[Collections.Generic.List[object]]::new()
$occupied=@{}
for($y=0;$y -lt $h;$y++){for($x=0;$x -lt $w;$x++){
 $c=$source.GetPixel($x*$cell+6,$y*$cell+6)
 if($c.R -eq 21 -and $c.G -eq 26 -and $c.B -eq 31){continue}
 $blocks.Add(@{id=8;x=$x;y=$y});$occupied["$x,$y"]=$true
}}
$sx=12;$sy=101
if($occupied["$sx,$sy"] -or $occupied["$sx,$($sy+1)"] -or -not $occupied["$sx,$($sy+2)"]){throw 'Spawn clearance failed'}
$blocks.Add(@{id=100;x=$sx;y=$sy})
$template=[IO.File]::ReadAllBytes((Join-Path $root '학습용/암벽.LMF'))
$stream=[IO.MemoryStream]::new()
$writer=[IO.BinaryWriter]::new($stream)
$writer.Write($template,0,32)
$stream.Position=16;$writer.Write([uint16]$w);$writer.Write([uint16]$h)
$stream.Position=21;$writer.Write([uint32]$blocks.Count)
$stream.Position=32
foreach($r in $blocks){$writer.Write([uint32]$r.id);$writer.Write([int16]$r.x);$writer.Write([int16]$r.y)}
$bytes=$stream.ToArray()
if($bytes.Length -ne 32+8*$blocks.Count){throw 'Length mismatch'}
for($i=0;$i -lt $blocks.Count;$i++){
 $p=32+$i*8
 if([BitConverter]::ToUInt32($bytes,$p) -ne $blocks[$i].id -or [BitConverter]::ToInt16($bytes,$p+4) -ne $blocks[$i].x -or [BitConverter]::ToInt16($bytes,$p+6) -ne $blocks[$i].y){throw 'Roundtrip mismatch'}
}
$dest=Join-Path $root '암벽_도트06.LMF'
[IO.File]::WriteAllBytes($dest,$bytes)
$preview=[Drawing.Bitmap]::new($source)
$g=[Drawing.Graphics]::FromImage($preview)
$g.FillEllipse([Drawing.Brushes]::Cyan,$sx*$cell,$sy*$cell,$cell,$cell)
$g.Dispose();$preview.Save((Join-Path $PSScriptRoot '암벽_도트06_미리보기.png'))
$preview.Dispose();$source.Dispose();$writer.Dispose();$stream.Dispose()
Write-Output "Saved $dest | ${w}x${h} | $($blocks.Count) records | exact approved silhouette | spawn ($sx,$sy) | roundtrip OK"
