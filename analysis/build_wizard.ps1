$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$root='C:\Users\microsoft\Desktop\로스트웨폰 맵'
$im=[Drawing.Bitmap]::FromFile('C:\Users\MICROS~1\AppData\Local\Temp\codex-clipboard-1eef21aa-1767-4964-bc9f-5f263eccd5bb.png')
# Trace the supplied silhouette, excluding the brown game background.
$outline=@(19,57,37,53,45,35,59,23,76,16,96,12,108,22,117,43,117,58,107,46,101,38,95,60,91,78,89,97,91,116,95,143,89,153,87,160,75,161,65,157,61,158,48,156,43,150,48,143,51,128,51,114,43,108,13,108,9,102,12,97,35,97,36,80,44,70,22,62)
$poly=New-Object Drawing.Drawing2D.GraphicsPath
$points=for($i=0;$i -lt $outline.Count;$i+=2){[Drawing.PointF]::new($outline[$i],$outline[$i+1])}
$poly.AddPolygon([Drawing.PointF[]]$points)
$records=[Collections.Generic.List[object]]::new()
for($y=0;$y -lt 81;$y++){for($x=0;$x -lt 60;$x++){
 $sx=[Math]::Min($im.Width-1,2*$x+1);$sy=[Math]::Min($im.Height-1,2*$y+1)
 if(!$poly.IsVisible([single]$sx,[single]$sy)){continue}
 $p=$im.GetPixel($sx,$sy);$r=[int]$p.R;$g=[int]$p.G;$b=[int]$p.B
 if($b -gt $r*1.15 -and $b -gt $g*1.12){$id=82}
 elseif($r -gt 140 -and $g -gt 130 -and $b -lt $g*.72 -and $sy -lt 78){$id=16}
 elseif($r -gt 105 -and $r -gt $g*1.6 -and $r -gt $b*1.5){$id=10}
 elseif(($r+$g+$b) -lt 220){$id=129}
 elseif($r -gt $b*1.2 -and $r -gt 140){$id=12}
 else{$id=0}
 $records.Add(@{id=$id;x=$x+4;y=$y+3})
}}
# Spawn on a separate small shelf, clear of the artwork.
for($x=1;$x -le 8;$x++){$records.Add(@{id=0;x=$x;y=88})}
$records.Add(@{id=100;x=3;y=86})
$header=[IO.File]::ReadAllBytes((Join-Path $root '영상\용암.LMF'))
$stream=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($stream)
$writer.Write($header,0,32);$stream.Position=16;$writer.Write([uint16]68);$writer.Write([uint16]92)
$stream.Position=21;$writer.Write([uint32]$records.Count);$stream.Position=32
foreach($q in $records){$writer.Write([uint32]$q.id);$writer.Write([int16]$q.x);$writer.Write([int16]$q.y)}
$dest=Join-Path $root '마법사_캐릭터도트.LMF';[IO.File]::WriteAllBytes($dest,$stream.ToArray())
$writer.Dispose();$stream.Dispose();$im.Dispose();$poly.Dispose()
# Render from the saved LMF, using the editor's actual tile bitmaps.
$data=[IO.File]::ReadAllBytes($dest);$count=[BitConverter]::ToUInt32($data,21)
if($data.Length -ne 32+8*$count){throw 'Invalid LMF length'}
$tm=Get-Content (Join-Path $root 'analysis\tilemap.json') -Raw|ConvertFrom-Json
$canvas=[Drawing.Bitmap]::new(544,736);$gfx=[Drawing.Graphics]::FromImage($canvas);$gfx.Clear([Drawing.Color]::FromArgb(26,29,37));$cache=@{}
for($o=32;$o -lt $data.Length;$o+=8){$id=[BitConverter]::ToUInt32($data,$o);$x=[BitConverter]::ToInt16($data,$o+4);$y=[BitConverter]::ToInt16($data,$o+6)
 if($x -lt 0 -or $x -ge 68 -or $y -lt 0 -or $y -ge 92){throw 'Out of bounds'}
 if(!$cache.ContainsKey($id)){$tile=[Drawing.Bitmap]::FromFile((Join-Path $root ('analysis\bitmap_'+$tm."$id"+'.bmp')));$tile.MakeTransparent([Drawing.Color]::Magenta);$cache[$id]=$tile}
 $gfx.DrawImage($cache[$id],$x*8,$y*8,8,8)
}
$canvas.Save((Join-Path $root 'analysis\마법사_캐릭터도트.png'))
$gfx.Dispose();$canvas.Dispose();foreach($tile in $cache.Values){$tile.Dispose()}
Write-Output "Validated: 68x92, $count records, $($data.Length) bytes. $dest"
