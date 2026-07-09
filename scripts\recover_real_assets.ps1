param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [string]$BuyersJson,
    [string]$LayoutConfig,
    [string]$InputPpt,
    [string]$OutputPpt,
    [string]$PreviewDir,
    [ValidateSet("light", "auto", "browser")][string]$AssetMode = "auto",
    [int]$BrowserTimeoutMs = 18000,
    [switch]$EnableAiVisualFallback,
    [switch]$SkipPptRefresh
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
    throw "Python executable not found."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Get-PythonExecutable
$scriptPath = Join-Path $PSScriptRoot "recover_real_assets.py"

$arguments = @(
    $scriptPath,
    "--workspace", $Workspace,
    "--asset-mode", $AssetMode,
    "--browser-timeout-ms", [string]$BrowserTimeoutMs
)

if ($BuyersJson) { $arguments += @("--buyers-json", $BuyersJson) }
if ($LayoutConfig) { $arguments += @("--layout-config", $LayoutConfig) }
if ($InputPpt) { $arguments += @("--input-ppt", $InputPpt) }
if ($OutputPpt) { $arguments += @("--output-ppt", $OutputPpt) }
if ($PreviewDir) { $arguments += @("--preview-dir", $PreviewDir) }
if ($EnableAiVisualFallback) { $arguments += "--enable-ai-visual-fallback" }
if ($SkipPptRefresh) { $arguments += "--skip-ppt-refresh" }

& $pythonExe @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Local real-asset recovery failed."
}

