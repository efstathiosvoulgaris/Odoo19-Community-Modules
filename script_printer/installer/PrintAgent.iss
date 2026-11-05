; Print Agent setup. Admin once: the browser policy below lives in HKLM
; (Software\Policies is not writable by a plain user, even under HKCU).
; Installs PrintAgent.exe + SumatraPDF.exe, starts the agent at every logon
; (per user: it must see that user's printers) and ends by opening the
; settings page, where the laser / thermal printers and copies are chosen.
; Build: build.ps1 in this folder.

#define AppName    "Print Agent"
#define AppVersion "2.0"

[Setup]
AppId={{5C2E8B71-3F4D-4A9C-9E21-7B6D0A4F1C83}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Efstathios Voulgaris
DefaultDirName={autopf}\PrintAgent
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
; 64-bit registry view: Chrome reads its policies there, not under WOW6432Node.
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=PrintAgent-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
UninstallDisplayIcon={app}\PrintAgent.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
#if FileExists(CompilerPath + "Languages\Greek.isl")
Name: "el"; MessagesFile: "compiler:Languages\Greek.isl"
#endif

[Files]
Source: "dist\PrintAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\SumatraPDF.exe"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; Chrome/Edge (142+) block an internet page from calling 127.0.0.1 unless the
; site is allowed: «Local Network Access». Whole PC, removed on uninstall.
; ponytail: only the current Odoo address; add the new one at the DNS switch.
Root: HKLM; Subkey: "Software\Policies\Google\Chrome\LocalNetworkAccessAllowedForUrls"; ValueType: string; ValueName: "1"; ValueData: "https://dev.eskarlas.gr"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Policies\Microsoft\Edge\LocalNetworkAccessAllowedForUrls"; ValueType: string; ValueName: "1"; ValueData: "https://dev.eskarlas.gr"; Flags: uninsdeletevalue

[Icons]
Name: "{commonstartup}\Print Agent"; Filename: "{app}\PrintAgent.exe"
Name: "{commondesktop}\Ρυθμίσεις Εκτύπωσης"; Filename: "http://127.0.0.1:8765/"

[Run]
Filename: "{app}\PrintAgent.exe"; Flags: nowait runasoriginaluser
Filename: "http://127.0.0.1:8765/"; Description: "Άνοιγμα Ρυθμίσεων Εκτύπωσης"; Flags: postinstall shellexec nowait

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/f /im PrintAgent.exe"; Flags: runhidden; RunOnceId: "KillAgent"
