#define AppName "SSKJ Camera Studio"
#define AppVersion "0.2.4"
#define AppPublisher "SSKJ"
#define AppExeName "SSKJCameraStudio.exe"

[Setup]
AppId={{9E710648-9568-4C66-A069-5282701827D8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\SSKJ Camera Studio
DefaultGroupName=SSKJ Camera Studio
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=SSKJ-Camera-Studio-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimpli.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "..\dist\SSKJCameraStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SSKJ Camera Studio"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\SSKJ Camera Studio"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 SSKJ Camera Studio"; Flags: nowait postinstall skipifsilent

[Messages]
BeveledLabel=SSKJ 原生虚拟摄像头
