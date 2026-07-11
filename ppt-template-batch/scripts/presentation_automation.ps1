function Start-PresentationAutomation {
    param(
        [ValidateSet("auto", "office", "wps")][string]$Engine = "auto"
    )

    $candidates = switch ($Engine) {
        "office" { @(@{ Name = "Office"; ProgId = "PowerPoint.Application" }) }
        "wps" { @(@{ Name = "WPS"; ProgId = "WPP.Application" }, @{ Name = "WPS"; ProgId = "KWPP.Application" }) }
        default { @(@{ Name = "Office"; ProgId = "PowerPoint.Application" }, @{ Name = "WPS"; ProgId = "WPP.Application" }, @{ Name = "WPS"; ProgId = "KWPP.Application" }) }
    }

    $errors = @()
    foreach ($candidate in $candidates) {
        try {
            $application = New-Object -ComObject $candidate.ProgId -ErrorAction Stop
            try { $application.Visible = -1 } catch { }
            return [PSCustomObject]@{ Application = $application; Engine = $candidate.Name }
        }
        catch {
            $errors += "$($candidate.Name): $($_.Exception.Message)"
        }
    }
    throw "No compatible presentation application is available. $($errors -join ' | ')"
}

function Stop-PresentationAutomation {
    param($Session)
    if ($null -eq $Session -or $null -eq $Session.Application) { return }
    try { $Session.Application.Quit() } catch { }
}
