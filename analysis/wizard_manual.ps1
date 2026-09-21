$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$b=[Drawing.Bitmap]::new(120,164);$g=[Drawing.Graphics]::FromImage($b);$g.Clear([Drawing.Color]::Transparent)
function Poly($color,$coords){$pts=for($i=0;$i -lt $coords.Count;$i+=2){[Drawing.Point]::new($coords[$i],$coords[$i+1])};$br=[Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($color));$g.FillPolygon($br,[Drawing.Point[]]$pts);$br.Dispose()}
function Oval($color,$x,$y,$w,$h){$br=[Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($color));$g.FillEllipse($br,$x,$y,$w,$h);$br.Dispose()}
# Separate silhouettes: cape, body, limbs, face, then hat over face.
Poly '#ee3020' @(76,96,87,103,90,124,95,147,82,155,73,146,72,110)
Poly '#951d24' @(86,109,90,126,95,147,86,150,83,131)
Oval '#eee8d4' 52 103 28 39
Oval '#c9c9c9' 66 127 16 24
Oval '#eee8d4' 62 131 15 23
Oval '#eee8d4' 46 141 19 13
Oval '#ffffff' 65 149 20 11
Oval '#ffffff' 51 112 11 19
Oval '#151515' 37 60 15 17
Oval '#151515' 75 69 15 18
Oval '#ffffff' 37 64 47 37
Oval '#c9c9c9' 38 84 36 16
Oval '#ffffff' 35 79 28 15
Oval '#151515' 44 67 13 13
Oval '#151515' 72 73 8 12
Oval '#151515' 35 83 7 5
# Carried gun and hands.
Poly '#151515' @(12,97,45,97,49,94,58,96,60,103,75,105,73,113,57,110,48,114,41,109,12,107)
Poly '#777777' @(11,99,41,99,42,103,12,103)
Poly '#c9c9c9' @(19,97,36,97,36,100,19,100)
Oval '#eee8d4' 52 100 10 12
# Hat: curved tall cone and drooping tip; broad asymmetric brim.
Poly '#3220d9' @(34,58,44,39,55,28,68,21,82,16,96,14,103,18,109,27,116,43,117,56,111,50,105,39,99,32,96,43,91,63,90,74,71,71,52,66,33,63,20,61,19,58)
Poly '#542eff' @(39,56,47,40,60,28,75,21,89,18,82,29,73,43,67,65,49,62)
Poly '#21118f' @(83,62,90,43,96,25,101,30,96,48,91,65,91,74,72,70)
function Star($x,$y,$s){Poly '#ffe35b' @($x,($y-$s),($x+1),($y-1),($x+$s),($y-1),($x+2),($y+1),($x+2),($y+$s),$x,($y+2),($x-2),($y+$s),($x-2),($y+1),($x-$s),($y-1),($x-1),($y-1))}
Star 48 54 5;Star 60 37 4;Star 73 23 4;Star 88 22 4;Star 102 27 4;Star 79 44 4;Star 67 59 5;Star 85 65 4
$g.Dispose()
$ids=@{'#EE3020'=49;'#951D24'=49;'#EEE8D4'=0;'#FFFFFF'=0;'#C9C9C9'=18;'#151515'=129;'#777777'=18;'#3220D9'=82;'#542EFF'=82;'#21118F'=82;'#FFE35B'=17}
$rec=[Collections.Generic.List[object]]::new()
for($y=0;$y -lt 82;$y++){for($x=0;$x -lt 60;$x++){$p=$b.GetPixel($x*2,$y*2);if($p.A -eq 0){continue};$hex='#{0:X2}{1:X2}{2:X2}' -f $p.R,$p.G,$p.B;$rec.Add(@{id=$ids[$hex];x=$x+4;y=$y+3})}}
$b.Dispose();for($x=1;$x -le 8;$x++){$rec.Add(@{id=0;x=$x;y=88})};$rec.Add(@{id=100;x=3;y=86})
$base=[IO.File]::ReadAllBytes((Resolve-Path '영상\용암.LMF'));$out=[byte[]]::new(32+8*$rec.Count);[Array]::Copy($base,$out,32)
[BitConverter]::GetBytes([uint16]68).CopyTo($out,16);[BitConverter]::GetBytes([uint16]92).CopyTo($out,18);[BitConverter]::GetBytes([uint32]$rec.Count).CopyTo($out,21)
$o=32;foreach($q in $rec){[BitConverter]::GetBytes([uint32]$q.id).CopyTo($out,$o);[BitConverter]::GetBytes([int16]$q.x).CopyTo($out,$o+4);[BitConverter]::GetBytes([int16]$q.y).CopyTo($out,$o+6);$o+=8}
[IO.File]::WriteAllBytes((Join-Path $pwd '마법사_수작업도트_v2.LMF'),$out)
$tm=Get-Content analysis\tilemap.json -Raw|ConvertFrom-Json;$canvas=[Drawing.Bitmap]::new(544,736);$g=[Drawing.Graphics]::FromImage($canvas);$g.Clear([Drawing.Color]::FromArgb(28,30,38));$cache=@{}
for($o=32;$o -lt $out.Length;$o+=8){$id=[BitConverter]::ToUInt32($out,$o);$x=[BitConverter]::ToInt16($out,$o+4);$y=[BitConverter]::ToInt16($out,$o+6);if(!$cache.ContainsKey($id)){$t=[Drawing.Bitmap]::FromFile((Join-Path $pwd ('analysis\bitmap_'+$tm."$id"+'.bmp')));$t.MakeTransparent([Drawing.Color]::Magenta);$cache[$id]=$t};$g.DrawImage($cache[$id],$x*8,$y*8,8,8)}
$canvas.Save((Join-Path $pwd 'analysis\마법사_수작업도트_v2.png'));$g.Dispose();$canvas.Dispose();foreach($t in $cache.Values){$t.Dispose()};"Saved $($rec.Count) blocks"
