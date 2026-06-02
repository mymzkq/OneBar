#define MyAppName "OneBar"
#define MyAppVersion "0.10.9"
#define MyAppPublisher "RainbowYX"
#define MyAppExeName "OneBar.exe"

[Setup]
AppId={{E8F15024-0AB3-4F1D-9F85-5E10B8D7345B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/mymzkq
AppSupportURL=https://github.com/mymzkq
DefaultDirName={localappdata}\Programs\OneBar
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist
OutputBaseFilename=OneBar_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "chinesetrad"; MessagesFile: "languages\ChineseTraditional.isl"

[CustomMessages]
english.AppDescription=OneBar is a lightweight top-mounted productivity island for Windows.
chinesesimp.AppDescription=OneBar 是一个常驻屏幕顶部的轻量 Windows 效率入口。
chinesetrad.AppDescription=OneBar 是一個常駐螢幕頂部的輕量 Windows 效率入口。
english.DesktopIcon=Create a desktop shortcut
chinesesimp.DesktopIcon=创建桌面快捷方式
chinesetrad.DesktopIcon=建立桌面捷徑
english.AdditionalIcons=Additional shortcuts
chinesesimp.AdditionalIcons=附加快捷方式
chinesetrad.AdditionalIcons=附加捷徑
english.LaunchOneBar=Launch OneBar
chinesesimp.LaunchOneBar=启动 OneBar
chinesetrad.LaunchOneBar=啟動 OneBar

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\OneBar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchOneBar}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := ExpandConstant('{cm:AppDescription}');
end;
