Add-Type -AssemblyName System.Drawing
$w=25; $h=104; $s=12
$mask=[Drawing.Bitmap]::new($w,$h)
$mg=[Drawing.Graphics]::FromImage($mask)
$mg.Clear([Drawing.Color]::Black)
function Rock($coords){
 $pts=[Drawing.Point[]]@($coords | ForEach-Object {[Drawing.Point]::new($_[0],$_[1])})
 $mg.FillPolygon([Drawing.Brushes]::White,$pts)
}
# Asymmetric continuous rock faces with carved bays and broken noses.
Rock @(@(0,0),@(9,0),@(8,2),@(6,3),@(6,5),@(3,7),@(2,10),@(3,13),@(6,15),@(8,16),@(7,18),@(5,18),@(3,20),@(2,24),@(2,29),@(4,32),@(7,34),@(8,36),@(6,37),@(4,36),@(2,38),@(1,43),@(2,46),@(5,47),@(7,49),@(9,50),@(8,52),@(6,52),@(5,54),@(2,55),@(2,61),@(4,64),@(6,66),@(5,68),@(3,67),@(1,70),@(1,74),@(3,77),@(7,78),@(10,80),@(9,82),@(7,82),@(4,81),@(2,84),@(2,89),@(4,92),@(7,93),@(8,95),@(6,97),@(3,97),@(2,101),@(0,103))
Rock @(@(24,0),@(21,0),@(22,5),@(21,9),@(18,11),@(17,13),@(14,14),@(15,16),@(18,17),@(21,15),@(22,19),@(21,23),@(18,25),@(16,26),@(15,29),@(17,30),@(19,29),@(21,31),@(22,36),@(21,40),@(18,41),@(16,43),@(17,45),@(20,46),@(22,49),@(22,53),@(20,55),@(16,56),@(14,58),@(16,60),@(18,60),@(21,58),@(23,63),@(22,68),@(19,71),@(17,73),@(18,75),@(21,74),@(22,79),@(22,83),@(20,86),@(17,88),@(16,90),@(19,91),@(22,89),@(23,96),@(21,100),@(24,103))
# Two distinct interior shards, with usable tops and tapered lower faces.
Rock @(@(10,23),@(12,22),@(13,24),@(12,26),@(12,29),@(10,28),@(9,26))
Rock @(@(11,62),@(13,63),@(14,66),@(13,69),@(12,70),@(12,67),@(10,65))
# Small isolated teeth, deliberately unlike repeated shelf strings.
$mg.FillRectangle([Drawing.Brushes]::White,11,39,1,1)
$mg.FillRectangle([Drawing.Brushes]::White,13,84,1,1)
$mg.FillRectangle([Drawing.Brushes]::White,12,96,2,1)
$mg.FillRectangle([Drawing.Brushes]::White,0,103,25,1)
$mg.Dispose()
$b=[Drawing.Bitmap]::new($w*$s,$h*$s)
$g=[Drawing.Graphics]::FromImage($b)
$g.Clear([Drawing.Color]::FromArgb(21,26,31))
$base=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(112,78,51))
$lip=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(166,122,75))
$shade=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(86,61,44))
for($y=0;$y -lt $h;$y++){for($x=0;$x -lt $w;$x++){
 if($mask.GetPixel($x,$y).R -eq 0){continue}
 $exposed=$y -gt 0 -and $mask.GetPixel($x,$y-1).R -eq 0
 $brush=$base
 if($exposed){$brush=$lip}
 elseif(($x*3+$y*2)%17 -eq 0){$brush=$shade}
 $g.FillRectangle($brush,$x*$s,$y*$s,$s,$s)
}}
$out=Join-Path $PSScriptRoot '암벽_도트초안_06.png'
$b.Save($out)
$g.Dispose();$b.Dispose();$mask.Dispose();$base.Dispose();$lip.Dispose();$shade.Dispose()
Write-Output $out
