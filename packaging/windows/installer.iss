[Setup]
AppId=ProxyProjectParticipantPilot
AppName=Proxy Project Participant Pilot
AppVersion=0.1.1
DefaultDirName={localappdata}\Programs\ProxyProject
DefaultGroupName=Proxy Project
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=ProxyProject-Setup-0.1.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ProxyProject.exe
CloseApplications=yes

[Files]
Source: "..\..\dist\ProxyProject\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Proxy Project"; Filename: "{app}\ProxyProject.exe"
Name: "{group}\Uninstall Proxy Project"; Filename: "{uninstallexe}"

[Messages]
FinishedLabel=The participant app is installed. It starts paused and never starts automatically. Launch it from the Start menu to read the disclosure and enroll.

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := MsgBox('Close the participant window before uninstalling. To revoke its gateway credential, use Withdraw consent in the app first. Local enrollment and usage state are retained to prevent quota resets. Continue?', mbConfirmation, MB_YESNO) = IDYES;
end;
