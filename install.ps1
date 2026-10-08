# Bony's Agents – Installer für Windows 10/11
#
# Installiert Python (falls nötig), QEMU und die Windows-Hypervisorplattform,
# richtet die App ein und legt Verknüpfungen auf dem Desktop und im Startmenü an.
# Am einfachsten per Doppelklick auf install.cmd starten.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Src    = $PSScriptRoot
$Base   = Join-Path $env:LOCALAPPDATA "bonys-agents"
$AppDir = Join-Path $Base "app"

function Say($text)  { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nFehler: $text" -ForegroundColor Red; Read-Host "Enter zum Beenden"; exit 1 }

function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-Python {
    # Bevorzugt den offiziellen Python-Launcher; der Store-Platzhalter in WindowsApps wird ignoriert.
    $candidates = New-Object System.Collections.Generic.List[object]
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates.Add([pscustomobject]@{ Exe = "py"; Args = @("-3") })
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") {
        $candidates.Add([pscustomobject]@{ Exe = $cmd.Source; Args = @() })
    }
    Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object { $candidates.Add([pscustomobject]@{ Exe = $_.FullName; Args = @() }) }
    foreach ($c in $candidates) {
        try {
            $a = $c.Args
            $ok = & $c.Exe @a -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
            if ($ok -eq "True") { return $c }
        } catch { }
    }
    return $null
}

# ---------- 1. winget ----------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail "winget fehlt. Bitte den 'App-Installer' aus dem Microsoft Store installieren und erneut starten."
}

# ---------- 2. Python ----------
Say "Prüfe Python …"
$py = Find-Python
if (-not $py) {
    Say "Installiere Python 3.12 …"
    winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
    Update-PathFromRegistry
    $py = Find-Python
    if (-not $py) { Fail "Python konnte nicht installiert werden." }
}
$pyExe = $py.Exe; $pyArgs = $py.Args
Write-Host ("Python: " + (& $pyExe @pyArgs --version))

# ---------- 3. App installieren ----------
Say "Installiere Bony's Agents nach $AppDir …"
& $pyExe @pyArgs -m venv $AppDir
if ($LASTEXITCODE -ne 0) { Fail "Virtuelle Python-Umgebung konnte nicht angelegt werden." }
$venvPy = Join-Path $AppDir "Scripts\python.exe"
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install $Src
if ($LASTEXITCODE -ne 0) { Fail "Installation der App fehlgeschlagen." }

# ---------- 4. QEMU + Hypervisorplattform ----------
Say "Installiere QEMU und schalte die Hardware-Beschleunigung ein (Windows fragt nach Zustimmung) …"
& (Join-Path $AppDir "Scripts\bonys-agents.exe") setup --yes
$setupCode = $LASTEXITCODE

# ---------- 5. Verknüpfungen ----------
Say "Lege Verknüpfungen an …"
$icon = Join-Path $Src "src\bonys_agents\resources\icon.ico"
$iconTarget = Join-Path $Base "icon.ico"
if (Test-Path $icon) { Copy-Item $icon $iconTarget -Force }
$gui = Join-Path $AppDir "Scripts\bonys-agents-gui.exe"
$shell = New-Object -ComObject WScript.Shell
$places = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($dir in $places) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Bony's Agents.lnk"))
    $lnk.TargetPath = $gui
    $lnk.WorkingDirectory = $Base
    $lnk.Description = "Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent"
    if (Test-Path $iconTarget) { $lnk.IconLocation = $iconTarget }
    $lnk.Save()
}

# ---------- 6. Fertig ----------
Write-Host ""
Write-Host "Fertig! 'Bony's Agents' liegt jetzt auf dem Desktop und im Startmenü." -ForegroundColor Green
if ($setupCode -ne 0) {
    Write-Host "Hinweis: Die Einrichtung von QEMU meldet noch ein Problem (siehe oben)." -ForegroundColor Yellow
    Write-Host "Die App zeigt beim Start, was fehlt, und kann es erneut versuchen."
}
Write-Host "Falls die Hypervisorplattform gerade eingeschaltet wurde: bitte Windows einmal neu starten." -ForegroundColor Yellow
$answer = Read-Host "Jetzt starten? (J/n)"
if ($answer -notmatch '^[nN]') { Start-Process $gui }
