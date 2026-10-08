; Inno-Setup-Skript für den Windows-Installer von Bony's Agents
;
; Bauen (nach PyInstaller):
;   iscc /DAppVersion=0.6.1 packaging\windows\bonys-agents.iss
; Ergebnis: dist\BonysAgents-Setup-<Version>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Bony's Agents"
#define AppExe "BonysAgents.exe"
#define CliExe "bonys-agents.exe"
#define Root "..\.."
#define YouTubeUrl "https://www.youtube.com/@BonysAgents"

[Setup]
AppId={{6E3B9C5A-1F4D-4B8E-9A21-B0A5E7C3D9F2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Bony
AppPublisherURL={#YouTubeUrl}
AppSupportURL={#YouTubeUrl}
AppUpdatesURL=https://github.com/zappotex/BonysAgents/releases
DefaultDirName={autopf}\Bony's Agents
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; GPL-3.0-or-later – wird vor der Installation angezeigt
LicenseFile={#Root}\LICENSE
SetupIconFile={#Root}\src\bonys_agents\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir={#Root}\dist
OutputBaseFilename=BonysAgents-Setup-{#AppVersion}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
; Bilder im Stil der App (erzeugt von packaging/make-resources.py), je 100 % und 200 % Skalierung
WizardImageFile=wizard-164.bmp,wizard-328.bmp
WizardSmallImageFile=wizard-small-55.bmp,wizard-small-110.bmp
; Für QEMU und die Windows-Hypervisorplattform sind Administratorrechte nötig.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Messages]
de.FinishedLabel=Bony's Agents ist jetzt installiert und im Startmenü zu finden.%n%nAuf YouTube zeige ich dir, wie du deinen ersten Agent-PC einrichtest: youtube.com/@BonysAgents
en.FinishedLabel=Bony's Agents is now installed and can be found in the Start menu.%n%nOn YouTube I show you how to set up your first agent PC: youtube.com/@BonysAgents

[CustomMessages]
de.TaskDesktop=Verknüpfung auf dem &Desktop anlegen
en.TaskDesktop=Create a &desktop shortcut
de.TaskDeps=QEMU und &Hardware-Beschleunigung jetzt automatisch einrichten (empfohlen)
en.TaskDeps=Set up QEMU and &hardware acceleration now (recommended)
de.StatusDeps=Richte QEMU und die Hardware-Beschleunigung ein – das kann einige Minuten dauern …
en.StatusDeps=Setting up QEMU and hardware acceleration – this may take a few minutes …
de.DepsFailed=QEMU konnte nicht automatisch eingerichtet werden. Bony's Agents zeigt beim Start, was fehlt, und kann es erneut versuchen.
en.DepsFailed=QEMU could not be set up automatically. Bony's Agents will show what is missing on start and can retry.
de.LaunchApp=Bony's Agents jetzt starten
en.LaunchApp=Launch Bony's Agents now
de.OpenYouTube=Anleitungen auf YouTube ansehen (youtube.com/@BonysAgents)
en.OpenYouTube=Watch the tutorials on YouTube (youtube.com/@BonysAgents)
de.KeepData=Deine Agent-PCs wurden nicht gelöscht. Sie liegen weiterhin in deinem Benutzerordner bzw. auf den gewählten Laufwerken.
en.KeepData=Your agent PCs were not deleted. They remain in your user folder or on the drives you chose.

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"
Name: "deps"; Description: "{cm:TaskDeps}"

[Files]
Source: "{#Root}\dist\bonys-agents\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "{#Root}\THIRD-PARTY-LICENSES"; DestDir: "{app}"; DestName: "THIRD-PARTY-LICENSES.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent runasoriginaluser
; Update aus der App heraus („/SILENT /RELAUNCH=1“): die App danach wieder starten
Filename: "{app}\{#AppExe}"; Flags: nowait postinstall skipifnotsilent runasoriginaluser; Check: IsRelaunch
Filename: "{#YouTubeUrl}"; Description: "{cm:OpenYouTube}"; Flags: postinstall shellexec runasoriginaluser nowait skipifsilent unchecked

[Code]
var
  RestartNeeded: Boolean;

function IsRelaunch(): Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('deps') then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('StatusDeps');
    WizardForm.ProgressGauge.Style := npbstMarquee;
    // "setup --yes" installiert QEMU (winget) und schaltet die Hypervisorplattform ein.
    // Rückgabe 3010 = Neustart nötig (wie bei Windows-Updates üblich).
    if Exec(ExpandConstant('{app}\{#CliExe}'), 'setup --yes', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    begin
      if Code = 3010 then
        RestartNeeded := True
      else if Code <> 0 then
        MsgBox(CustomMessage('DepsFailed'), mbInformation, MB_OK);
    end;
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
end;

function NeedRestart(): Boolean;
begin
  Result := RestartNeeded;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox(CustomMessage('KeepData'), mbInformation, MB_OK);
end;
