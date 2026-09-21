Add-Type -AssemblyName System.Drawing
$root=Split-Path $PSScriptRoot -Parent
$w=31;$h=168;$s=8
$mask=[Drawing.Bitmap]::new($w,$h)
$mg=[Drawing.Graphics]::FromImage($mask);$mg.Clear([Drawing.Color]::Black)
$src=[Drawing.Bitmap]::FromFile((Join-Path $PSScriptRoot '암벽_도트초안_06.png'))
# Keep the approved lower silhouette; widen its open spaces by six cells.
for($y=0;$y -lt 104;$y++){for($x=0;$x -lt $w;$x++){
 $ox=[Math]::Min(24,[int][Math]::Floor($x*25/31))
 $c=$src.GetPixel($ox*12+6,$y*12+6)
 if($c.R -ne 21){$mask.SetPixel($x,$y+64,[Drawing.Color]::White)}
}}
$src.Dispose()
function Mass($q){$pts=[Drawing.Point[]]@($q|ForEach-Object{[Drawing.Point]::new($_[0],$_[1])});$mg.FillPolygon([Drawing.Brushes]::White,$pts)}
# A new upper ravine: blunt headwall, hanging tooth, narrow chimney and summit.
Mass @(@(0,0),@(10,0),@(10,3),@(7,4),@(4,7),@(3,11),@(5,14),@(9,16),@(10,18),@(7,19),@(5,18),@(2,22),@(2,28),@(4,31),@(8,34),@(10,35),@(9,38),@(6,38),@(3,36),@(2,41),@(3,44),@(5,46),@(4,49),@(2,50),@(2,55),@(5,58),@(10,61),@(11,64),@(0,64))
Mass @(@(30,0),@(27,0),@(27,6),@(24,10),@(21,11),@(19,14),@(22,15),@(25,14),@(28,17),@(28,22),@(25,25),@(23,28),@(24,30),@(27,29),@(29,33),@(28,39),@(25,42),@(20,44),@(18,46),@(20,48),@(24,48),@(27,46),@(29,52),@(28,57),@(26,61),@(27,64),@(30,64))
Mass @(@(14,23),@(16,24),@(17,28),@(16,32),@(15,34),@(14,31),@(14,28),@(12,26))
# Remove two isolated catch tiles from the approved draft. Keep the lower start tooth.
$mg.FillRectangle([Drawing.Brushes]::Black,13,103,3,1)
$mg.FillRectangle([Drawing.Brushes]::Black,16,148,3,1)
$mg.Dispose()
$records=[Collections.Generic.List[object]]::new()
$preview=[Drawing.Bitmap]::new($w*$s,$h*$s);$g=[Drawing.Graphics]::FromImage($preview);$g.Clear([Drawing.Color]::FromArgb(21,26,31))
$base=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(112,78,51));$top=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(166,122,75))
for($y=0;$y -lt $h;$y++){for($x=0;$x -lt $w;$x++){
 if($mask.GetPixel($x,$y).R -eq 0){continue}
 $records.Add(@{id=8;x=$x;y=$y})
 $brush=$base;if($y -gt 0 -and $mask.GetPixel($x,$y-1).R -eq 0){$brush=$top}
 $g.FillRectangle($brush,$x*$s,$y*$s,$s,$s)
}}
$sx=15;$sy=165
if($mask.GetPixel($sx,$sy).R -ne 0 -or $mask.GetPixel($sx,$sy+1).R -ne 0 -or $mask.GetPixel($sx,$sy+2).R -eq 0){throw 'Spawn obstructed'}
$records.Add(@{id=100;x=$sx;y=$sy});$g.FillEllipse([Drawing.Brushes]::Cyan,$sx*$s,$sy*$s,$s,$s)
$g.Dispose();$preview.Save((Join-Path $PSScriptRoot '암벽_긴협곡07_미리보기.png'))
$header=[IO.File]::ReadAllBytes((Join-Path $root '학습용/암벽.LMF'))
$stream=[IO.MemoryStream]::new();$bw=[IO.BinaryWriter]::new($stream);$bw.Write($header,0,32)
$stream.Position=16;$bw.Write([uint16]$w);$bw.Write([uint16]$h);$stream.Position=21;$bw.Write([uint32]$records.Count);$stream.Position=32
foreach($r in $records){$bw.Write([uint32]$r.id);$bw.Write([int16]$r.x);$bw.Write([int16]$r.y)}
$bytes=$stream.ToArray();if($bytes.Length -ne 32+8*$records.Count){throw 'Invalid size'}
[IO.File]::WriteAllBytes((Join-Path $root '암벽_긴협곡07.LMF'),$bytes)
$bw.Dispose();$stream.Dispose();$mask.Dispose();$preview.Dispose();$base.Dispose();$top.Dispose()
Write-Output "31x168 | $($records.Count) records | spawn clear | gameplay reach not measured"
