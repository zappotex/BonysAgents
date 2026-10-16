# Baut die Windows-Installer beider Editionen (BonysAgents-Setup-<Version>.exe und
# BonysAgents-Kursleiter-Setup-<Version>.exe) auf einem Windows-PC.
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

# ---------- Programm bündeln (beide Editionen) ----------
Say "Bündle das Programm (PyInstaller) …"
& $py -m venv build\venv-win
if ($LASTEXITCODE -ne 0) { Fail "venv fehlgeschlagen" }
& build\venv-win\Scripts\python.exe -m pip install -q --upgrade pip
& build\venv-win\Scripts\python.exe packaging\fetch-novnc.py
if ($LASTEXITCODE -ne 0) { Fail "noVNC konnte nicht geladen werden" }
# Feste Versionen mit Prüfsummen (packaging\requirements-build.txt), danach nur noch das eigene Paket
& build\venv-win\Scripts\python.exe -m pip install -q --require-hashes -r packaging\requirements-build.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen" }
& build\venv-win\Scripts\python.exe -m pip install -q --no-deps --no-build-isolation .
if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen" }

$outs = @()
foreach ($edition in @("anwender", "kursleiter")) {
    $dist = if ($edition -eq "kursleiter") { "bonys-agents-kursleiter" } else { "bonys-agents" }
    Say "Edition: $edition"
    & build\venv-win\Scripts\pyinstaller.exe --noconfirm --log-level WARN --workpath "build\pyinstaller-$edition" `
        packaging\bonys-agents.spec -- --edition $edition
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller fehlgeschlagen ($edition)" }
    & build\venv-win\Scripts\python.exe packaging\collect-licenses.py "dist\$dist"
    if ($LASTEXITCODE -ne 0) { Fail "Lizenztexte ließen sich nicht sammeln ($edition)" }
    & build\venv-win\Scripts\python.exe packaging\check-edition.py "dist\$dist" $edition
    if ($LASTEXITCODE -ne 0) { Fail "Die Edition $edition enthält nicht das Richtige." }

    # Kurztest des gebündelten Programms
    & "dist\$dist\bonys-agents.exe" --version
    if ($LASTEXITCODE -ne 0) { Fail "Das gebündelte Programm startet nicht ($edition)." }

    Say "Baue den Installer (Inno Setup, $edition) …"
    & $iscc /Q "/DAppVersion=$version" "/DEdition=$edition" packaging\windows\bonys-agents.iss
    if ($LASTEXITCODE -ne 0) { Fail "Inno Setup fehlgeschlagen ($edition)" }
}

$out = Join-Path $Root "dist\BonysAgents-Setup-$version.exe"
Write-Host "`nFertig: $out" -ForegroundColor Green
Write-Host "       $(Join-Path $Root "dist\BonysAgents-Kursleiter-Setup-$version.exe")" -ForegroundColor Green
Start-Process explorer.exe "/select,`"$out`""
Read-Host "Enter zum Beenden"
