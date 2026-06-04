$ErrorActionPreference = "Stop"

Write-Host "[INFO] Searching for Odoo Windows Service..."
$odooService = Get-CimInstance Win32_Service -Filter "Name like '%odoo%'" | Select-Object -First 1

if (-not $odooService) {
    Write-Host "[WARNING] No Odoo service found — skipping addon removal and service restart."
    exit
}

Write-Host "[INFO] Found Odoo Service: $($odooService.Name)"

# Derive the addons path from the service executable location
$exePath = ($odooService.PathName -replace '"').Trim()
$serverPath = Split-Path $exePath
$addonsPath = Join-Path $serverPath "addons"
$addonTarget = Join-Path $addonsPath "direct_print"

Write-Host "[INFO] Looking for addon at: $addonTarget"

if (Test-Path $addonTarget) {
    Remove-Item $addonTarget -Recurse -Force
    Write-Host "[INFO] 'direct_print' addon removed from: $addonTarget"
} else {
    Write-Host "[WARNING] 'direct_print' addon not found at expected path — may have been removed already or installed elsewhere."
}

# Remove wkhtmltopdf from system PATH if it was added by the installer
$thirdPartyPath = Join-Path (Split-Path $serverPath) "thirdparty"
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($machinePath -match [regex]::Escape($thirdPartyPath)) {
    $newPath = ($machinePath -split ";" | Where-Object { $_ -ne $thirdPartyPath }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Host "[INFO] Removed wkhtmltopdf from System PATH."
}

Write-Host "[INFO] Restarting Odoo Service to clear cache..."
try {
    Restart-Service -Name $odooService.Name -Force
    Write-Host "[INFO] Service restarted."
} catch {
    Write-Host "[WARNING] Could not restart Odoo service: $_"
}
