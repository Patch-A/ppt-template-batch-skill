param(
    [Parameter(Mandatory = $true)][string]$InputPpt,
    [Parameter(Mandatory = $true)][string]$PreviewDir,
    [ValidateSet("auto", "office", "wps")][string]$Engine = "auto"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputPpt)) {
    throw "Input PPT not found."
}

New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null
$stagingRoot = Join-Path $env:TEMP ("ppt-preview-" + [Guid]::NewGuid().ToString("N"))
$stagedInput = Join-Path $stagingRoot "input.pptx"
$stagedPreviews = Join-Path $stagingRoot "previews"
New-Item -ItemType Directory -Force -Path $stagedPreviews | Out-Null
Copy-Item -LiteralPath $InputPpt -Destination $stagedInput -Force
. (Join-Path $PSScriptRoot "presentation_automation.ps1")
$session = Start-PresentationAutomation -Engine $Engine
$powerPoint = $session.Application

try {
    $presentation = $powerPoint.Presentations.Open($stagedInput, $true, $false, $false)
    $presentation.Export($stagedPreviews, "PNG")
    $presentation.Close()
    Copy-Item -Path (Join-Path $stagedPreviews "*.PNG") -Destination $PreviewDir -Force
}
finally {
    Stop-PresentationAutomation -Session $session
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output $PreviewDir
