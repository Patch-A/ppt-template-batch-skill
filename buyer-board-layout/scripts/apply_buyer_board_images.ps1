param(
    [Parameter(Mandatory = $true)][string]$InputPpt,
    [Parameter(Mandatory = $true)][string]$BuyersJson,
    [Parameter(Mandatory = $true)][string]$LayoutConfigJson,
    [Parameter(Mandatory = $true)][string]$OutputPpt,
    [Parameter(Mandatory = $true)][string]$PreviewDir
)

$ErrorActionPreference = "Stop"

function Get-PythonExecutable {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    $fallback = "C:\Users\root\AppData\Local\Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }
    throw "Python executable not found. It is required for image preprocessing."
}

function Prepare-ImageAsset {
    param(
        [string]$ImagePath,
        [ValidateSet("logo", "site")][string]$Kind,
        [double]$TargetWidth = 0,
        [double]$TargetHeight = 0
    )

    $pythonExe = Get-PythonExecutable
    $scriptPath = Join-Path $PSScriptRoot "prepare_layout_image.py"
    $arguments = @(
        $scriptPath,
        "--input",
        $ImagePath,
        "--kind",
        $Kind
    )
    if ($Kind -eq "site") {
        $arguments += @(
            "--target-width",
            [string][int][Math]::Round($TargetWidth),
            "--target-height",
            [string][int][Math]::Round($TargetHeight)
        )
    }
    $output = & $pythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Image preprocessing failed for $ImagePath"
    }
    return ($output | Select-Object -Last 1).Trim()
}

function Get-ShapeAtPosition {
    param(
        $Slide,
        [double]$Left,
        [double]$Top,
        [int[]]$AllowedTypes = @(13, 28)
    )

    foreach ($shape in $Slide.Shapes) {
        if ($AllowedTypes -notcontains $shape.Type) {
            continue
        }
        if ([Math]::Abs($shape.Left - $Left) -lt 2 -and [Math]::Abs($shape.Top - $Top) -lt 2) {
            return $shape
        }
    }

    throw "Target shape not found at expected position."
}

function Fit-PictureIntoBox {
    param(
        $Shape,
        [double]$BoxLeft,
        [double]$BoxTop,
        [double]$BoxWidth,
        [double]$BoxHeight
    )

    $ratio = [Math]::Min($BoxWidth / $Shape.Width, $BoxHeight / $Shape.Height)
    $Shape.LockAspectRatio = -1
    $Shape.Width = $Shape.Width * $ratio
    $Shape.Height = $Shape.Height * $ratio
    $Shape.Left = $BoxLeft + (($BoxWidth - $Shape.Width) / 2)
    $Shape.Top = $BoxTop + (($BoxHeight - $Shape.Height) / 2)
}

function Fill-PictureIntoBox {
    param(
        $Shape,
        [double]$BoxLeft,
        [double]$BoxTop,
        [double]$BoxWidth,
        [double]$BoxHeight
    )

    $ratio = [Math]::Max($BoxWidth / $Shape.Width, $BoxHeight / $Shape.Height)
    $Shape.LockAspectRatio = -1
    $Shape.Width = $Shape.Width * $ratio
    $Shape.Height = $Shape.Height * $ratio
    $Shape.Left = $BoxLeft + (($BoxWidth - $Shape.Width) / 2)
    $Shape.Top = $BoxTop + (($BoxHeight - $Shape.Height) / 2)
}

function Replace-PictureShape {
    param(
        $Slide,
        $Target,
        [string]$ImagePath,
        [bool]$FillBox = $false
    )

    if (-not (Test-Path -LiteralPath $ImagePath)) {
        throw "Missing image asset: $ImagePath"
    }

    $left = $Target.Left
    $top = $Target.Top
    $width = $Target.Width
    $height = $Target.Height
    $zOrder = $Target.ZOrderPosition

    $preparedImagePath = $ImagePath
    if ($FillBox) {
        $preparedImagePath = Prepare-ImageAsset -ImagePath $ImagePath -Kind "site" -TargetWidth $width -TargetHeight $height
    }

    $Target.Delete()
    $newShape = $Slide.Shapes.AddPicture($preparedImagePath, $false, $true, $left, $top, -1, -1)
    if ($FillBox) {
        Fill-PictureIntoBox -Shape $newShape -BoxLeft $left -BoxTop $top -BoxWidth $width -BoxHeight $height
    }
    else {
        Fit-PictureIntoBox -Shape $newShape -BoxLeft $left -BoxTop $top -BoxWidth $width -BoxHeight $height
    }

    while ($newShape.ZOrderPosition -lt $zOrder) {
        $newShape.ZOrder(0)
    }
}

function Remove-PictureTarget {
    param(
        $Slide,
        [double]$Left,
        [double]$Top
    )

    $target = Get-ShapeAtPosition -Slide $Slide -Left $Left -Top $Top -AllowedTypes @(13)
    $target.Delete()
}

function Add-LogoPicture {
    param(
        $Slide,
        [string]$ImagePath,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height
    )

    if (-not (Test-Path -LiteralPath $ImagePath)) {
        throw "Missing image asset: $ImagePath"
    }

    $preparedImagePath = Prepare-ImageAsset -ImagePath $ImagePath -Kind "logo"
    $shape = $Slide.Shapes.AddPicture($preparedImagePath, $false, $true, $Left, $Top, -1, -1)
    Fit-PictureIntoBox -Shape $shape -BoxLeft $Left -BoxTop $Top -BoxWidth $Width -BoxHeight $Height
}

function Remove-HeaderArtifacts {
    param(
        $Slide,
        [double]$Left,
        [double]$Top,
        [double]$Right,
        [double]$Bottom
    )

    $toDelete = @()
    foreach ($shape in $Slide.Shapes) {
        if (
            $shape.Left -ge $Left -and
            $shape.Left -le $Right -and
            $shape.Top -ge $Top -and
            $shape.Top -le $Bottom -and
            ($shape.Type -eq 28 -or $shape.Type -eq 13)
        ) {
            $toDelete += $shape
        }
    }

    foreach ($shape in $toDelete) {
        $shape.Delete()
    }
}

if (-not (Test-Path -LiteralPath $InputPpt)) {
    throw "Input PPT not found."
}

if (-not (Test-Path -LiteralPath $BuyersJson)) {
    throw "Buyers JSON not found."
}

if (-not (Test-Path -LiteralPath $LayoutConfigJson)) {
    throw "Layout config JSON not found."
}

$buyers = Get-Content -Raw -Encoding UTF8 -LiteralPath $BuyersJson | ConvertFrom-Json
$layout = Get-Content -Raw -Encoding UTF8 -LiteralPath $LayoutConfigJson | ConvertFrom-Json
$slideAssets = @{}
foreach ($item in $layout.images.slides) {
    $slideAssets[[int]$item.slide_offset] = $item
}
$startSlideIndex = [int]$layout.content.start_slide_index
New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null

$powerPoint = New-Object -ComObject PowerPoint.Application
$powerPoint.Visible = -1

try {
    $presentation = $powerPoint.Presentations.Open($InputPpt, $false, $false, $false)

    for ($index = 0; $index -lt $buyers.Count; $index++) {
        $buyer = $buyers[$index]
        $slot = $slideAssets[$index]
        if ($null -eq $slot) {
            continue
        }

        $slide = $presentation.Slides.Item($startSlideIndex + $index)

        if ($null -ne $slot.site -and -not [string]::IsNullOrWhiteSpace([string]$buyer.site_image_path)) {
            $siteTarget = Get-ShapeAtPosition -Slide $slide -Left ([double]$slot.site.target_left) -Top ([double]$slot.site.target_top) -AllowedTypes @(13)
            $fillBox = $false
            if ($null -ne $slot.site.fill) {
                $fillBox = [bool]$slot.site.fill
            }
            Replace-PictureShape -Slide $slide -Target $siteTarget -ImagePath $buyer.site_image_path -FillBox $fillBox
        }
        elseif ($null -ne $slot.site) {
            Remove-PictureTarget -Slide $slide -Left ([double]$slot.site.target_left) -Top ([double]$slot.site.target_top)
        }

        if ($null -eq $slot.logo) {
            continue
        }

        if ([string]::IsNullOrWhiteSpace([string]$buyer.logo_path)) {
            if ($slot.logo.mode -eq "replace") {
                Remove-PictureTarget -Slide $slide -Left ([double]$slot.logo.target_left) -Top ([double]$slot.logo.target_top)
            }
            elseif ($null -ne $slot.logo.clear_region) {
                Remove-HeaderArtifacts `
                    -Slide $slide `
                    -Left ([double]$slot.logo.clear_region.left) `
                    -Top ([double]$slot.logo.clear_region.top) `
                    -Right ([double]$slot.logo.clear_region.right) `
                    -Bottom ([double]$slot.logo.clear_region.bottom)
            }
            continue
        }

        if ($slot.logo.mode -eq "add") {
            if ($null -ne $slot.logo.clear_region) {
                Remove-HeaderArtifacts `
                    -Slide $slide `
                    -Left ([double]$slot.logo.clear_region.left) `
                    -Top ([double]$slot.logo.clear_region.top) `
                    -Right ([double]$slot.logo.clear_region.right) `
                    -Bottom ([double]$slot.logo.clear_region.bottom)
            }

            Add-LogoPicture `
                -Slide $slide `
                -ImagePath $buyer.logo_path `
                -Left ([double]$slot.logo.left) `
                -Top ([double]$slot.logo.top) `
                -Width ([double]$slot.logo.width) `
                -Height ([double]$slot.logo.height)
        }
        else {
            $logoTarget = Get-ShapeAtPosition -Slide $slide -Left ([double]$slot.logo.target_left) -Top ([double]$slot.logo.target_top) -AllowedTypes @(13)
            Replace-PictureShape -Slide $slide -Target $logoTarget -ImagePath $buyer.logo_path
        }
    }

    $presentation.SaveAs($OutputPpt)
    $presentation.Export($PreviewDir, "PNG")
    $presentation.Close()
}
finally {
    $powerPoint.Quit()
}

Write-Output $OutputPpt
Write-Output $PreviewDir
