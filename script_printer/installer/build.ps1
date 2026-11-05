<#
    Builds Output\PrintAgent-<version>-Setup.exe.
      1. PyInstaller -> dist\PrintAgent.exe (one file, no console)
      2. Inno Setup  -> Output\PrintAgent-2.0-Setup.exe
    Needs Python (pip install pyinstaller) and Inno Setup 6 (winget install JRSoftware.InnoSetup).
#>
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
try {
    python -m PyInstaller --onefile --noconsole --name PrintAgent --distpath dist --workpath build --specpath build ..\agent\print_agent.py
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
              "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 not found: winget install JRSoftware.InnoSetup' }
    & $iscc PrintAgent.iss
} finally { Pop-Location }
