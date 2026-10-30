#ifndef ScriptVersion
#define ScriptVersion "3.1"
#endif
#ifndef PayloadDir
#define PayloadDir "..\dist\WinYandexMusicRPC-gui"
#endif
[Setup]
AppId=WinYandexMusicRPC
AppName=WinYandexMusicRPC
AppVersion={#ScriptVersion}
AppPublisher=FozerG
AppPublisherURL=https://github.com/FozerG/WinYandexMusicRPC
DefaultDirName={autopf}\WinYandexMusicRPC
DefaultGroupName=WinYandexMusicRPC
OutputDir=..\dist
OutputBaseFilename=WinYandexMusicRPC_Setup_{#ScriptVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=classic dark includetitlebar
WizardSizePercent=110,110
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=no
SetupIconFile=..\assets\YMRPC_ico.ico
WizardImageFile=welcome.png
WizardSmallImageFile=icon.png
WizardSmallImageBackColor=#202020
WizardImageAlphaFormat=premultiplied
UninstallDisplayIcon={app}\WinYandexMusicRPC.exe
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
AllowRootDirectory=no
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
UninstallLogging=yes
[LangOptions]
DialogFontName=Segoe UI
DialogFontSize=10

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
#include "messages.iss"
[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "*.debug.pak,__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "{cm:Desktop}"; Flags: checkedonce
Name: "startmenu"; Description: "{cm:StartMenu}"; Flags: checkedonce
[Icons]
Name: "{autoprograms}\WinYandexMusicRPC\WinYandexMusicRPC"; Filename: "{app}\WinYandexMusicRPC.exe"; Tasks: startmenu
Name: "{autodesktop}\WinYandexMusicRPC"; Filename: "{app}\WinYandexMusicRPC.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\WinYandexMusicRPC.exe"; Description: "{cm:Run}"; Flags: nowait postinstall skipifsilent runasoriginaluser
[Code]
#include "integration.iss"
#include "appearance.iss"
