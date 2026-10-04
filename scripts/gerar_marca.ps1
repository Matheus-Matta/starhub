# Gera as imagens da marca a partir de static/starhub/img/logo.png e favicon.png
# (fundo transparente): favicon-32/192, apple-touch-icon, marca-64 (simbolo),
# logo-600 e logo-600-escuro ("Star" em branco para o tema escuro).
# Uso: powershell -File scripts/gerar_marca.ps1   (troque os PNGs de origem e rode de novo)
Add-Type -AssemblyName System.Drawing
$img = Join-Path $PSScriptRoot "..\static\starhub\img"

function Redimensionar($origem, $largura, $altura) {
  $nova = New-Object System.Drawing.Bitmap($largura, $altura, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($nova)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $g.Clear([System.Drawing.Color]::Transparent)
  $g.DrawImage($origem, 0, 0, $largura, $altura)
  $g.Dispose()
  return $nova
}

# Caixa do que nao e transparente (numa copia pequena, para ser rapido).
function Recorte($bmp) {
  $escala = 4
  $mini = Redimensionar $bmp ([int]($bmp.Width / $escala)) ([int]($bmp.Height / $escala))
  $x0 = $mini.Width; $y0 = $mini.Height; $x1 = 0; $y1 = 0
  for ($y = 0; $y -lt $mini.Height; $y++) { for ($x = 0; $x -lt $mini.Width; $x++) {
    if ($mini.GetPixel($x, $y).A -gt 20) {
      if ($x -lt $x0) { $x0 = $x }; if ($x -gt $x1) { $x1 = $x }
      if ($y -lt $y0) { $y0 = $y }; if ($y -gt $y1) { $y1 = $y }
    } } }
  $mini.Dispose()
  $m = 2
  $x0 = [Math]::Max(0, ($x0 - $m) * $escala); $y0 = [Math]::Max(0, ($y0 - $m) * $escala)
  $x1 = [Math]::Min($bmp.Width, ($x1 + $m + 1) * $escala); $y1 = [Math]::Min($bmp.Height, ($y1 + $m + 1) * $escala)
  return New-Object System.Drawing.Rectangle($x0, $y0, ($x1 - $x0), ($y1 - $y0))
}

function Cortar($bmp) {
  $r = Recorte $bmp
  return $bmp.Clone($r, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
}

# Simbolo (favicon): quadrado, recortado.
$fav = New-Object System.Drawing.Bitmap("$img\favicon.png")
$simbolo = Cortar $fav
$lado = [Math]::Max($simbolo.Width, $simbolo.Height)
$quadrado = New-Object System.Drawing.Bitmap($lado, $lado, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($quadrado); $g.Clear([System.Drawing.Color]::Transparent)
$g.DrawImage($simbolo, [int](($lado - $simbolo.Width) / 2), [int](($lado - $simbolo.Height) / 2), $simbolo.Width, $simbolo.Height); $g.Dispose()
foreach ($t in 32, 64, 180, 192) {
  $s = Redimensionar $quadrado $t $t
  $nome = @{32 = "favicon-32.png"; 64 = "marca-64.png"; 180 = "apple-touch-icon.png"; 192 = "favicon-192.png"}[$t]
  $s.Save("$img\$nome", [System.Drawing.Imaging.ImageFormat]::Png); $s.Dispose()
}

# Logo: recortado, 600px de largura; e a versao para o tema escuro ("Star" em branco).
$logo = New-Object System.Drawing.Bitmap("$img\logo.png")
$cortado = Cortar $logo
$alt = [int](600 * $cortado.Height / $cortado.Width)
$pequeno = Redimensionar $cortado 600 $alt
$pequeno.Save("$img\logo-600.png", [System.Drawing.Imaging.ImageFormat]::Png)
for ($y = 0; $y -lt $pequeno.Height; $y++) { for ($x = 0; $x -lt $pequeno.Width; $x++) {
  $p = $pequeno.GetPixel($x, $y)
  # Azul-marinho do "Star" (escuro e pouco saturado); o gradiente do "Hub" fica.
  if ($p.A -gt 0 -and $p.R -lt 70 -and $p.G -lt 70 -and $p.B -lt 120 -and ($p.B - $p.R) -lt 90) {
    $pequeno.SetPixel($x, $y, [System.Drawing.Color]::FromArgb($p.A, 245, 247, 250))
  } } }
$pequeno.Save("$img\logo-600-escuro.png", [System.Drawing.Imaging.ImageFormat]::Png)
"logo ${alt}px de altura; simbolo ${lado}px"
Get-ChildItem $img -Filter *.png | Select-Object Name, Length | Format-Table -AutoSize | Out-String
