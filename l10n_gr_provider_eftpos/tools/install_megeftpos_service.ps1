<#
.SYNOPSIS
    Registers the MegEftPos REST driver as a Windows service (Α.1155 EFT/POS).

.DESCRIPTION
    MegEftPosRestServices.exe is a real ServiceBase binary — it already knows
    how to be a service, so this only tells the SCM about it. No wrapper.

    Run elevated. Double-click Install-MegEftPos-Service.cmd instead if you
    would rather not open a shell.

.PARAMETER DriverPath
    Folder holding MegEftPosRestServices.exe. Defaults to C:\Odoo\MegEftPosDriver.

.PARAMETER Uninstall
    Stop and remove the service. Leaves the files and the licence alone.

.EXAMPLE
    .\install_megeftpos_service.ps1
    .\install_megeftpos_service.ps1 -DriverPath D:\MegEftPosDriver
    .\install_megeftpos_service.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$DriverPath = 'C:\Odoo\MegEftPosDriver',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

# The SCM name is NOT free choice: MegEftPosRestServices.exe is a .NET
# ServiceBase and Windows matches the name it was started under against the
# ServiceName compiled into the binary. Any other name starts, then dies with
# «Error 1083: the executable does not implement the service».
$ServiceName = 'MegEftPosRestServices'
$DisplayName = 'MegEftPos Driver (Α.1155 EFT/POS)'
$Description = 'REST driver for card payments and Α.1155 payment signatures. ' +
               'Odoo talks to it over http://localhost:8187.'

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this elevated (Start > PowerShell > Run as administrator), ' +
              'or double-click Install-MegEftPos-Service.cmd.'
    }
}

function Get-DriverPort {
    # Read the port the driver was configured with rather than assuming 8187,
    # so the verification below checks the right one.
    $config = Join-Path $DriverPath 'MegEftPosRestServices.config'
    if (Test-Path $config) {
        foreach ($line in Get-Content $config) {
            if ($line -match '^\s*rest\.server\.port\s*=\s*(\d+)') { return [int]$Matches[1] }
        }
    }
    return 8187
}

Assert-Admin
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
    if (-not $existing) {
        Write-Host "Service '$ServiceName' is not installed — nothing to do."
        return
    }
    if ($existing.Status -ne 'Stopped') {
        Write-Host "Stopping $ServiceName ..."
        Stop-Service -Name $ServiceName -Force
        (Get-Service $ServiceName).WaitForStatus('Stopped', '00:00:30')
    }
    & sc.exe delete $ServiceName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "sc.exe delete failed ($LASTEXITCODE)." }
    Write-Host "Removed. The driver files and licence are untouched." -ForegroundColor Green
    return
}

# ------------------------------------------------------------------ install
$exe = Join-Path $DriverPath 'MegEftPosRestServices.exe'
if (-not (Test-Path $exe)) {
    throw "MegEftPosRestServices.exe not found in '$DriverPath'. Pass -DriverPath."
}
# The Standalone .exe is the console build and cannot run as a service; a
# missing licence lets the service start and then refuse every transaction.
if (-not (Get-ChildItem -Path (Join-Path $DriverPath 'MegEftPos') -Filter '*.lic' -ErrorAction SilentlyContinue)) {
    Write-Warning "No .lic file under '$DriverPath\MegEftPos' — the driver will start but reject transactions."
}

if ($existing) {
    Write-Host "Service exists; pointing it at '$exe' and leaving it installed."
    & sc.exe config $ServiceName binPath= "$exe" start= auto DisplayName= "$DisplayName" | Out-Null
} else {
    Write-Host "Creating service '$ServiceName' ..."
    & sc.exe create $ServiceName binPath= "$exe" start= auto DisplayName= "$DisplayName" | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw "sc.exe returned $LASTEXITCODE." }

& sc.exe description $ServiceName "$Description" | Out-Null
# A till mid-shift should not need a human to notice the driver died: restart
# after 5s, 10s, then every 30s, with the counter forgetting a bad day after 24h.
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null

Write-Host "Starting ..."
Start-Service -Name $ServiceName
(Get-Service $ServiceName).WaitForStatus('Running', '00:00:30')

# --------------------------------------------------------------- verify
# Installed-and-running is not the same as answering: a bad config or a port
# already taken leaves the service Running with a dead listener.
$port = Get-DriverPort
$listening = $false
foreach ($attempt in 1..10) {
    Start-Sleep -Milliseconds 500
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        $listening = $true
        break
    }
}

Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
if ($listening) {
    Write-Host "OK — listening on http://localhost:$port" -ForegroundColor Green
    Write-Host "Set this URL on the terminal in Odoo (Λογιστική > Πάροχος > Τερματικά EFT/POS)."
} else {
    Write-Warning "Service is Running but nothing is listening on port $port."
    Write-Warning "Check $DriverPath\MegEftPosRestServicesLogs\ and rest.server.port in MegEftPosRestServices.config."
}
