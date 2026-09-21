Add-Type -AssemblyName System.Drawing
$d=Get-Content (Join-Path $PSScriptRoot 'cliff09_repaired.json') -Raw|ConvertFrom-Json
$s=6;$b=[Drawing.Bitmap]::new(186,1440);$g=[Drawing.Graphics]::FromImage($b);$g.Clear([Drawing.Color]::FromArgb(21,26,31));$cells=@{}
foreach($r in $d.records){$cells["$($r.x),$($r.y)"]=$r.id}
$stone=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(112,78,51));$lip=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(166,122,75))
foreach($r in $d.records){$br=$stone;if(-not $cells.ContainsKey("$($r.x),$($r.y-1)")){$br=$lip};if($r.id -eq 100){$br=[Drawing.Brushes]::Cyan};$g.FillRectangle($br,$r.x*$s,$r.y*$s,$s,$s)}
$g.Dispose();$b.Save((Join-Path $PSScriptRoot '암벽09_연결수정_미리보기.png'));$b.Dispose();$stone.Dispose();$lip.Dispose()
