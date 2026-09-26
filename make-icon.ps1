Add-Type -AssemblyName System.Drawing
$bitmap = New-Object System.Drawing.Bitmap 512,512
$g = [System.Drawing.Graphics]::FromImage($bitmap)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$sage = [System.Drawing.ColorTranslator]::FromHtml('#829B87')
$white = [System.Drawing.ColorTranslator]::FromHtml('#FFFFFF')
$g.Clear($sage)
$brush = New-Object System.Drawing.SolidBrush $white
$pen = New-Object System.Drawing.Pen $white,14
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddArc(117,83,48,48,180,90)
$path.AddArc(345,83,48,48,270,90)
$path.AddArc(345,357,48,48,0,90)
$path.AddArc(117,357,48,48,90,90)
$path.CloseFigure()
$g.DrawPath($pen,$path)
$g.DrawLine($pen,161,89,161,398)
$thin = New-Object System.Drawing.Pen $white,7
$g.DrawLine($thin,180,369,372,369)
$bookmark = [System.Drawing.Point[]]@((New-Object System.Drawing.Point 318,91),(New-Object System.Drawing.Point 349,91),(New-Object System.Drawing.Point 349,159),(New-Object System.Drawing.Point 333,147),(New-Object System.Drawing.Point 318,159))
$g.FillPolygon($brush,$bookmark)
$font = New-Object System.Drawing.Font 'Georgia',74,([System.Drawing.FontStyle]::Bold),([System.Drawing.GraphicsUnit]::Pixel)
$format = New-Object System.Drawing.StringFormat
$format.Alignment = 'Center'
$format.LineAlignment = 'Center'
$g.DrawString('Me',$font,$brush,([System.Drawing.RectangleF]::new(174,172,205,162)),$format)
$bitmap.Save((Join-Path $PSScriptRoot 'static\icon-512.png'),[System.Drawing.Imaging.ImageFormat]::Png)
foreach($size in @(180,192)) {
  $small = New-Object System.Drawing.Bitmap $size,$size
  $sg = [System.Drawing.Graphics]::FromImage($small)
  $sg.InterpolationMode = 'HighQualityBicubic'
  $sg.DrawImage($bitmap,0,0,$size,$size)
  $small.Save((Join-Path $PSScriptRoot "static\icon-$size.png"),[System.Drawing.Imaging.ImageFormat]::Png)
  $sg.Dispose(); $small.Dispose()
}
$g.Dispose();$bitmap.Dispose();$brush.Dispose();$pen.Dispose();$thin.Dispose();$path.Dispose();$font.Dispose();$format.Dispose()
