Add-Type -AssemblyName System.Drawing
$root=Split-Path $PSScriptRoot -Parent
$w=31;$h=240;$s=6
$mask=[Drawing.Bitmap]::new($w,$h);$mg=[Drawing.Graphics]::FromImage($mask);$mg.Clear([Drawing.Color]::Black)
function Mass($q){$pts=[Drawing.Point[]]@($q|ForEach-Object{[Drawing.Point]::new($_[0],$_[1])});$mg.FillPolygon([Drawing.Brushes]::White,$pts)}
# Hand drawn, asymmetric faces. Each nose has a different shoulder and undercut.
Mass @(@(0,0),@(13,0),@(12,3),@(8,4),@(5,7),@(4,12),@(6,16),@(10,18),@(12,20),@(9,22),@(6,21),@(3,25),@(3,31),@(5,34),@(9,36),@(11,37),@(10,39),@(6,39),@(4,42),@(3,47),@(5,49),@(8,50),@(7,52),@(4,53),@(2,58),@(3,64),@(6,68),@(10,69),@(13,72),@(11,74),@(8,73),@(5,75),@(3,79),@(2,84),@(4,87),@(7,88),@(8,90),@(5,92),@(3,91),@(2,97),@(3,102),@(5,105),@(10,107),@(12,110),@(9,111),@(6,110),@(3,115),@(2,120),@(4,124),@(8,126),@(10,128),@(8,130),@(5,130),@(3,134),@(3,140),@(5,142),@(8,143),@(7,145),@(4,147),@(2,151),@(3,157),@(6,160),@(10,161),@(12,164),@(10,166),@(7,165),@(4,168),@(2,173),@(2,180),@(5,183),@(9,184),@(10,187),@(7,188),@(4,187),@(2,191),@(3,198),@(5,202),@(9,204),@(12,205),@(11,208),@(7,208),@(4,211),@(3,215),@(4,220),@(7,222),@(10,224),@(9,226),@(6,226),@(3,230),@(2,235),@(0,239))
Mass @(@(30,0),@(27,0),@(28,6),@(26,10),@(22,13),@(18,14),@(17,16),@(20,18),@(24,16),@(27,20),@(28,24),@(27,29),@(24,32),@(22,34),@(23,36),@(26,35),@(28,39),@(27,44),@(23,47),@(18,48),@(16,51),@(19,53),@(23,52),@(26,55),@(28,61),@(27,65),@(24,67),@(23,69),@(26,70),@(28,74),@(28,79),@(25,82),@(21,83),@(18,85),@(19,87),@(24,88),@(27,91),@(28,96),@(26,99),@(23,101),@(21,102),@(23,104),@(26,104),@(28,109),@(27,115),@(24,117),@(20,118),@(17,121),@(20,123),@(24,122),@(27,126),@(28,132),@(26,135),@(23,137),@(24,139),@(27,140),@(28,145),@(25,149),@(20,151),@(17,153),@(19,155),@(23,155),@(27,158),@(28,164),@(27,168),@(23,171),@(21,173),@(24,175),@(27,173),@(29,178),@(28,183),@(25,186),@(21,188),@(18,191),@(20,193),@(24,192),@(27,195),@(28,200),@(27,206),@(24,209),@(21,210),@(22,212),@(26,213),@(28,217),@(27,222),@(24,225),@(19,226),@(17,228),@(20,230),@(24,229),@(27,232),@(28,237),@(30,239))
# Small edge notches: wall-supported, not floating stepping stones.
$teeth=@(@(26,219),@(26,216),@(3,218),@(3,214),@(26,181),@(25,178),@(3,178),@(4,175),@(26,163),@(25,160),@(3,155),@(4,152),@(26,144),@(25,141),@(3,138),@(4,135),@(26,113),@(26,110),@(3,100),@(3,96),@(26,94),@(25,91),@(3,82),@(4,78),@(26,77),@(25,74),@(3,63),@(4,60),@(26,59),@(25,56),@(3,46),@(4,43),@(26,28),@(25,25),@(3,30),@(4,27))
foreach($p in $teeth){$x=$p[0];$y=$p[1];if($x -lt 15){$mg.FillRectangle([Drawing.Brushes]::White,0,$y,$x+1,2)}else{$mg.FillRectangle([Drawing.Brushes]::White,$x,$y,31-$x,2)}}
$mg.FillRectangle([Drawing.Brushes]::White,0,239,31,1);$mg.Dispose()
$records=[Collections.Generic.List[object]]::new()
$preview=[Drawing.Bitmap]::new($w*$s,$h*$s);$g=[Drawing.Graphics]::FromImage($preview);$g.Clear([Drawing.Color]::FromArgb(21,26,31))
$base=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(112,78,51));$lip=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(166,122,75))
for($y=0;$y -lt $h;$y++){for($x=0;$x -lt $w;$x++){if($mask.GetPixel($x,$y).R -eq 0){continue};$records.Add(@{id=8;x=$x;y=$y});$br=$base;if($y -gt 0 -and $mask.GetPixel($x,$y-1).R -eq 0){$br=$lip};$g.FillRectangle($br,$x*$s,$y*$s,$s,$s)}}
# Three timed hazards on wide rock surfaces; preserve an adjacent clear standing cell.
$hazards=[Collections.Generic.List[object]]::new()
foreach($band in @(184,126,47)){
 $done=$false
 for($y=$band;$y -le $band+4 -and -not $done;$y++){for($x=4;$x -lt 27 -and -not $done;$x++){
  if($mask.GetPixel($x,$y).R -eq 255 -and $mask.GetPixel($x+1,$y).R -eq 255 -and $mask.GetPixel($x,$y-1).R -eq 0 -and $mask.GetPixel($x,$y-2).R -eq 0 -and $mask.GetPixel($x+1,$y-1).R -eq 0 -and $mask.GetPixel($x+1,$y-2).R -eq 0){$r=@{id=119;x=$x;y=$y-1};$records.Add($r);$hazards.Add($r);$g.FillRectangle([Drawing.Brushes]::IndianRed,$x*$s,($y-1)*$s,$s,$s);$done=$true}
 }}
}
$sx=15;$sy=237
if($mask.GetPixel($sx,$sy).R -ne 0 -or $mask.GetPixel($sx,$sy+1).R -ne 0){throw 'Spawn blocked'}
$records.Add(@{id=100;x=$sx;y=$sy});$g.FillEllipse([Drawing.Brushes]::Cyan,$sx*$s,$sy*$s,$s,$s)
$g.Dispose();$preview.Save((Join-Path $PSScriptRoot '암벽_깎인능선09_미리보기.png'))
$b0=[IO.File]::ReadAllBytes((Join-Path $root '학습용/암벽.LMF'));$ms=[IO.MemoryStream]::new();$bw=[IO.BinaryWriter]::new($ms);$bw.Write($b0,0,32);$ms.Position=16;$bw.Write([uint16]$w);$bw.Write([uint16]$h);$ms.Position=21;$bw.Write([uint32]$records.Count);$ms.Position=32
foreach($r in $records){$bw.Write([uint32]$r.id);$bw.Write([int16]$r.x);$bw.Write([int16]$r.y)}
$bytes=$ms.ToArray();if($bytes.Length -ne 32+8*$records.Count){throw 'Size mismatch'}
[IO.File]::WriteAllBytes((Join-Path $root '암벽_깎인능선09.LMF'),$bytes)
$bw.Dispose();$ms.Dispose();$mask.Dispose();$preview.Dispose();$base.Dispose();$lip.Dispose()
Write-Output "31x240 / $($records.Count) blocks / $($hazards.Count) supported timed spikes / spawn clear; traversal unverified"
