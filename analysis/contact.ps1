Add-Type -AssemblyName System.Drawing
$imgs = (Get-Content analysis/resources.json -Raw | ConvertFrom-Json).imgs
$sheet = New-Object System.Drawing.Bitmap 1000,([int][Math]::Ceiling($imgs.Count/10)*100)
$g = [System.Drawing.Graphics]::FromImage($sheet)
$g.Clear([System.Drawing.Color]::LightGray)
$font = New-Object System.Drawing.Font 'Arial',10
for($i=0;$i -lt $imgs.Count;$i++) { $it=$imgs[$i]; $im=[System.Drawing.Image]::FromFile((Join-Path $pwd ('analysis/'+$it.name))); $x=($i%10)*100; $y=[Math]::Floor($i/10)*100; $g.DrawImage($im,[int]$x,[int]$y,([int][Math]::Min(70,$im.Width)),([int][Math]::Min(70,$im.Height))); $g.DrawString([string]$it.id,$font,[System.Drawing.Brushes]::Black,[single]$x,[single]($y+76)); $im.Dispose() }
$sheet.Save((Join-Path $pwd 'analysis/tiles.png'),[System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose();$sheet.Dispose()
