#define ScriptVersion "2.4.1"
[Setup]
AppName=WinYandexMusicRPC
AppPublisher=FozerG
AppVersion={#ScriptVersion}
DefaultDirName={pf}\WinYandexMusicRPC
DefaultGroupName=WinYandexMusicRPC
OutputDir=dist
AppId=WinYandexMusicRPC
OutputBaseFilename=WinYandexMusicRPC_Installer_{#ScriptVersion}
Compression=lzma
SolidCompression=yes
DisableDirPage=yes       
DisableProgramGroupPage=yes
ShowLanguageDialog=no
SetupIconFile=assets\YMRPC_ico.ico
WizardImageFile=assets\YMRPC_large_bmp.bmp
WizardSmallImageFile=assets\YMRPC_bmp.bmp
WizardImageAlphaFormat=defined
PrivilegesRequired=admin
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
Source: "dist\WinYandexMusicRPC-cli\WinYandexMusicRPC.exe"; DestDir: "{pf}\WinYandexMusicRPC"; Flags: ignoreversion
Source: "dist\WinYandexMusicRPC-cli\_internal\*"; DestDir: "{pf}\WinYandexMusicRPC\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WinYandexMusicRPC"; Filename: "{pf}\WinYandexMusicRPC\WinYandexMusicRPC.exe"
Name: "{autodesktop}\WinYandexMusicRPC"; Filename: "{pf}\WinYandexMusicRPC\WinYandexMusicRPC.exe"; Tasks: desktopicon

[Code]
procedure UninstallPreviousVersion; //Удаление версии 2.4, так как установка в AppData оказалась неудачным решением.
var
  OldUninstallString: string;
  ResultCode: Integer;
begin
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{9b1a69af-4040-4080-8afd-97131cba7e21}}_is1', 'UninstallString', OldUninstallString) then
  begin
    Log('Обнаружена предыдущая версия. Запуск деинсталляции...');
    if (Pos('"', OldUninstallString) = 1) and (Copy(OldUninstallString, Length(OldUninstallString), 1) = '"') then
      OldUninstallString := Copy(OldUninstallString, 2, Length(OldUninstallString) - 2);
    if Exec(OldUninstallString, '/VERYSILENT /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        Log('Деинсталляция предыдущей версии завершена успешно.')
      else
        Log('Ошибка при деинсталляции предыдущей версии. Код результата: ' + IntToStr(ResultCode));
  end
  else
  begin
    Log('Предыдущая версия не обнаружена.');
  end;
end;

procedure DeleteStartupShortcut;
var
  StartupShortcut: string;
begin
  // Получаем путь к ярлыку в автозагрузке
  StartupShortcut := ExpandConstant('{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup\YaMusicRPC.lnk');
  
  // Проверяем, существует ли ярлык, и удаляем его, если он есть
  if FileExists(StartupShortcut) then
  begin
    DeleteFile(StartupShortcut);
  end;
end;

procedure DeleteRegistryEntry;
var
  RunKey: string;
begin
  // Определяем путь к ключу реестра
  RunKey := 'Software\Microsoft\Windows\CurrentVersion\Run';

  // Проверяем, существует ли запись реестра, и удаляем её, если она есть
  if RegValueExists(HKEY_CURRENT_USER, RunKey, 'YaMusicRPC') then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, RunKey, 'YaMusicRPC');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Выполняем действия только после завершения удаления программы
  if CurUninstallStep = usPostUninstall then
  begin
    DeleteStartupShortcut;
    DeleteRegistryEntry;
  end;
end;

procedure InitializeWizard;
begin
  UninstallPreviousVersion;
end;

[Run]
Filename: "{pf}\WinYandexMusicRPC\WinYandexMusicRPC.exe"; Description: "{cm:RunDescription}"; Flags: nowait postinstall skipifsilent

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktop}"; GroupDescription: "{cm:AdditionalTasks}"

[UninstallDelete]
Type: files; Name: "{pf}\WinYandexMusicRPC\_internal\*"
Type: dirifempty; Name: "{pf}\WinYandexMusicRPC\_internal"
Type: files; Name: "{pf}\WinYandexMusicRPC\WinYandexMusicRPC.exe"
Type: dirifempty; Name: "{pf}\WinYandexMusicRPC"
