param(
    [string]$Json = (Join-Path $PSScriptRoot '암벽_수학형_v1_후보.json'),
    [string]$Output = (Join-Path $PSScriptRoot '암벽_수학형_v1_미리보기.png')
)

Add-Type -AssemblyName System.Drawing
$d = Get-Content -Raw -LiteralPath $Json | ConvertFrom-Json
$scale = 4
$pad = 24
$w = [int]$d.width * $scale + $pad * 2
$h = [int]$d.height * $scale + $pad * 2
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(18, 21, 27))

$rock = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(134, 101, 67))
$edge = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(205, 170, 116), 1)
$startBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(70, 200, 120))
$goalBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 185, 70))
$font = New-Object System.Drawing.Font('Segoe UI', 8)
$textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 235, 235))

foreach ($cell in $d.solid_cells) {
    $x = $pad + [int]$cell[0] * $scale
    $y = $pad + [int]$cell[1] * $scale
    $g.FillRectangle($rock, $x, $y, $scale, $scale)
}

$sx = $pad + [int]$d.start.x * $scale
$sy = $pad + [int]$d.start.y * $scale
$g.FillEllipse($startBrush, $sx - 3, $sy - 3, 7, 7)
$gx = $pad + [int]$d.goal.x * $scale
$gy = $pad + [int]$d.goal.y * $scale
$g.FillEllipse($goalBrush, $gx - 3, $gy - 3, 7, 7)

$g.DrawRectangle($edge, $pad, $pad, [int]$d.width * $scale, [int]$d.height * $scale)
$g.DrawString('START', $font, $textBrush, $sx + 6, $sy - 5)
$g.DrawString('TOP', $font, $textBrush, $gx + 6, $gy - 5)

$g.Dispose()
$rock.Dispose()
$edge.Dispose()
$startBrush.Dispose()
$goalBrush.Dispose()
$font.Dispose()
$textBrush.Dispose()
$bmp.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output $Output
