# Baut den Windows-Installer (BonysAgents-Setup-<Version>.exe) auf einem Windows-PC.
#
# Einfach build-setup.cmd doppelklicken. Fehlendes (Python, Inno Setup) wird
# automatisch über winget installiert. Ergebnis liegt danach im Ordner "dist".

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Say($t)  { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host "`nFehler: $t" -ForegroundColor Red; Read-Host "Enter zum Beenden"; exit 1 }
function Update-PathFromRegistry {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

$version = (Select-String -Path "src\bonys_agents\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Say "Baue Bony's Agents $version"

# ---------- Python ----------
$py = $null
foreach ($c in @("py", "python")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $py = $cmd.Source; break }
}
if (-not $py) {
    Say "Installiere Python 3.12 …"
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    Update-PathFromRegistry
    $py = (Get-Command py -ErrorAction SilentlyContinue).Source
    if (-not $py) { Fail "Python konnte nicht installiert werden." }
}

# ---------- Inno Setup ----------
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Say "Installiere Inno Setup …"
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { Fail "Inno Setup konnte nicht installiert werden." }
}

# ---------- Programm bündeln ----------
Say "Bündle das Programm (PyInstaller) …"
& $py -m venv build\venv-win
if ($LASTEXITCODE -ne 0) { Fail "venv fehlgeschlagen" }
& build\venv-win\Scripts\python.exe -m pip install -q --upgrade pip
& build\venv-win\Scripts\python.exe -m pip install -q . pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen" }
& build\venv-win\Scripts\pyinstaller.exe --noconfirm --log-level WARN packaging\bonys-agents.spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller fehlgeschlagen" }

# Kurztest des gebündelten Programms
& dist\bonys-agents\bonys-agents.exe --version
if ($LASTEXITCODE -ne 0) { Fail "Das gebündelte Programm startet nicht." }

# ---------- Installer ----------
Say "Baue den Installer (Inno Setup) …"
& $iscc /Q "/DAppVersion=$version" packaging\windows\bonys-agents.iss
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup fehlgeschlagen" }

$out = Join-Path $Root "dist\BonysAgents-Setup-$version.exe"
Write-Host "`nFertig: $out" -ForegroundColor Green
Start-Process explorer.exe "/select,`"$out`""
Read-Host "Enter zum Beenden"
