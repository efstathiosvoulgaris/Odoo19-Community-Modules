$ErrorActionPreference = "Stop"

Write-Host "[INFO] Searching for Odoo Windows Service..."
$odooService = Get-CimInstance Win32_Service -Filter "Name like '%odoo%'" | Select-Object -First 1

if (-not $odooService) {
    Write-Host "[WARNING] No Odoo service found - skipping PATH and service steps."
    exit
}

Write-Host "[INFO] Found Odoo Service: $($odooService.Name)"

$exePath = ($odooService.PathName -replace '"').Trim()
$serverPath = Split-Path $exePath

# Add wkhtmltopdf (bundled with Odoo) to the system PATH so Odoo can find it
$thirdPartyPath = Join-Path (Split-Path $serverPath) "thirdparty"
if (Test-Path "$thirdPartyPath\wkhtmltopdf.exe") {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($machinePath -notmatch [regex]::Escape($thirdPartyPath)) {
        [Environment]::SetEnvironmentVariable("Path", $machinePath + ";" + $thirdPartyPath, "Machine")
        Write-Host "[INFO] Added wkhtmltopdf to System PATH."
    } else {
        Write-Host "[INFO] wkhtmltopdf already in System PATH."
    }
} else {
    Write-Host "[WARNING] wkhtmltopdf.exe not found at $thirdPartyPath - skipping PATH update."
}

Write-Host "[INFO] Restarting Odoo Service..."
Restart-Service -Name $odooService.Name -Force
Write-Host "[INFO] Service restarted."
