Add-Type -AssemblyName System.Drawing
$files=@(Get-ChildItem analysis/climb_video -Filter 'f*.jpg' | Sort-Object Name)
for($page=0;$page -lt 6;$page++){
$b=[System.Drawing.Bitmap]::new(1920,1980);$g=[System.Drawing.Graphics]::FromImage($b);$g.Clear([System.Drawing.Color]::Black);$font=[System.Drawing.Font]::new('Arial',15)
for($i=0;$i -lt 9;$i++){$idx=$page*30+$i*3;if($idx -ge $files.Count){continue};$im=[System.Drawing.Image]::FromFile($files[$idx].FullName);$x=($i%3)*640;$y=[Math]::Floor($i/3)*660;$g.DrawImage($im,[int]$x,[int]$y,640,650);$g.DrawString(($idx/2).ToString()+'s',$font,[System.Drawing.Brushes]::White,[single]$x,[single]$y);$im.Dispose()}
$b.Save((Join-Path $pwd ('analysis/climb_video/page'+$page+'.jpg')));$g.Dispose();$b.Dispose();$font.Dispose()}
