param(
    [Parameter(Mandatory = $true)][string]$InputPpt,
    [Parameter(Mandatory = $true)][string]$OutputPpt,
    [Parameter(Mandatory = $true)][int]$SourceSlideIndex,
    [Parameter(Mandatory = $true)][int]$CopyCount
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputPpt)) {
    throw "Input PPT not found."
}
if ($SourceSlideIndex -lt 1 -or $CopyCount -lt 0) {
    throw "Source slide index and copy count are invalid."
}

$stagingRoot = Join-Path $env:TEMP ("ppt-duplicate-" + [Guid]::NewGuid().ToString("N"))
$stagedInput = Join-Path $stagingRoot "input.pptx"
$stagedOutput = Join-Path $stagingRoot "output.pptx"
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPpt) | Out-Null
Copy-Item -LiteralPath $InputPpt -Destination $stagedInput -Force
$powerPoint = New-Object -ComObject PowerPoint.Application
$powerPoint.Visible = -1

try {
    $presentation = $powerPoint.Presentations.Open($stagedInput, $false, $false, $false)
    if ($SourceSlideIndex -gt $presentation.Slides.Count) {
        throw "Source slide is outside the presentation."
    }
    for ($offset = 1; $offset -le $CopyCount; $offset++) {
        $presentation.Slides.Item($SourceSlideIndex).Copy()
        $presentation.Slides.Paste($SourceSlideIndex + $offset) | Out-Null
    }
    $presentation.SaveAs($stagedOutput)
    $presentation.Close()
    Copy-Item -LiteralPath $stagedOutput -Destination $OutputPpt -Force
}
finally {
    $powerPoint.Quit()
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output $OutputPpt
