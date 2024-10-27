#define ScriptVersion "2.4"
[Setup]
AppName=WinYandexMusicRPC
AppPublisher=FozerG
AppVersion={#ScriptVersion}
DefaultDirName={localappdata}\WinYandexMusicRPC
DefaultGroupName=WinYandexMusicRPC
OutputDir=dist
AppId={{9b1a69af-4040-4080-8afd-97131cba7e21}}
OutputBaseFilename=WinYandexMusicRPC_Installer_{#ScriptVersion}
Compression=lzma
SolidCompression=yes
DisableDirPage=yes       
DisableProgramGroupPage=yes
ShowLanguageDialog=no
SetupIconFile=assets\YMRPC_ico.ico
WizardImageFile=assets\YMRPC_bmp.bmp
WizardSmallImageFile=assets\YMRPC_bmp.bmp
WizardImageAlphaFormat=defined
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\WinYandexMusicRPC.exe
Uninstallable=yes  
AllowRootDirectory=no
AlwaysRestart=no 
MinVersion=10.0.17763

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.RunDescription=Run WinYandexMusicRPC
english.CreateDesktop=Create a desktop icon
english.AdditionalTasks=Additional tasks
russian.RunDescription=Запустить WinYandexMusicRPC
russian.CreateDesktop=Создать значок на рабочем столе
russian.AdditionalTasks=Дополнительные задачи

[Files]
Source: "dist\WinYandexMusicRPC-cli\WinYandexMusicRPC.exe"; DestDir: "{localappdata}\WinYandexMusicRPC"; Flags: ignoreversion
Source: "dist\WinYandexMusicRPC-cli\_internal\*"; DestDir: "{localappdata}\WinYandexMusicRPC\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Добавляем ярлык для запуска приложения в меню "Пуск"
Name: "{group}\WinYandexMusicRPC"; Filename: "{localappdata}\WinYandexMusicRPC\WinYandexMusicRPC.exe"
Name: "{autodesktop}\WinYandexMusicRPC"; Filename: "{localappdata}\WinYandexMusicRPC\WinYandexMusicRPC.exe"; Tasks: desktopicon



[Run]
; Запуск exe файла после завершения установки
Filename: "{localappdata}\WinYandexMusicRPC\WinYandexMusicRPC.exe"; Description: "{cm:RunDescription}"; Flags: nowait postinstall skipifsilent
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktop}"; GroupDescription: "{cm:AdditionalTasks}"

[UninstallDelete]
Type: files; Name: "{localappdata}\WinYandexMusicRPC\_internal\*"
Type: dirifempty; Name: "{localappdata}\WinYandexMusicRPC\_internal"
Type: files; Name: "{localappdata}\WinYandexMusicRPC\WinYandexMusicRPC.exe"
Type: dirifempty; Name: "{localappdata}\WinYandexMusicRPC"
