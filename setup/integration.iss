const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
function GetDesktopWindow: HWND;
  external 'GetDesktopWindow@user32.dll stdcall';
function GetWindow(Wnd: HWND; Command: Cardinal): HWND;
  external 'GetWindow@user32.dll stdcall';
function GetWindowThreadProcessId(Wnd: HWND; var PID: Cardinal): Cardinal;
  external 'GetWindowThreadProcessId@user32.dll stdcall';
function PostMessage(Wnd: HWND; Msg: Cardinal; WParam, LParam: NativeInt): Boolean;
  external 'PostMessageW@user32.dll stdcall';

function CloseApp: Boolean;
var
  Locator, Service, Processes, Process: Variant;
  I, Attempt: Integer;
  PID, WindowPID: Cardinal;
  Wnd: HWND;
  Target: String;
begin
  Result := False;
  Target := ExpandConstant('{app}\WinYandexMusicRPC.exe');
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('', 'root\CIMV2');
    for Attempt := 0 to 2 do begin
      Processes := Service.ExecQuery('SELECT * FROM Win32_Process WHERE Name="WinYandexMusicRPC.exe"');
      Result := True;
      for I := 0 to Processes.Count - 1 do begin
        Process := Processes.ItemIndex(I);
        if not VarIsNull(Process.ExecutablePath) then
          if CompareText(Process.ExecutablePath, Target) = 0 then begin
            Result := False;
            PID := Process.ProcessId;
            if Attempt = 0 then begin
              Wnd := GetWindow(GetDesktopWindow, 5);
              while Wnd <> 0 do begin
                GetWindowThreadProcessId(Wnd, WindowPID);
                if WindowPID = PID then PostMessage(Wnd, $0010, 0, 0);
                Wnd := GetWindow(Wnd, 2);
              end;
            end else if Attempt = 1 then Process.Terminate(0);
          end;
      end;
      if Result then Exit;
      if Attempt < 2 then Sleep(800);
    end;
  except
    Result := False;
    Log('Closing application failed: ' + GetExceptionMessage);
  end;
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CloseApp then Result := CustomMessage('CloseFailed');
end;
function InitializeUninstall: Boolean;
begin
  Result := CloseApp;
  if not Result then MsgBox(CustomMessage('CloseFailed'), mbError, MB_OK);
end;
function SafeDataTree(const Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := True;
  if not DirExists(Path) then Exit;
  if FindFirst(Path, Entry) then begin
    Result := (Entry.Attributes and $400) = 0;
    FindClose(Entry);
  end else Result := False;
  if not Result then Exit;
  if FindFirst(AddBackslash(Path) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
          if (Entry.Attributes and $400) <> 0 then Result := False
          else if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := SafeDataTree(AddBackslash(Path) + Entry.Name);
          if not Result then Break;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;
procedure RemoveDataFolder(const Path: String);
begin
  if not DirExists(Path) then Exit;
  if SafeDataTree(Path) then
    if DelTree(Path, True, True, True) then Exit;
  Log('Data retained: ' + Path);
  if not UninstallSilent then
    MsgBox(FmtMessage(CustomMessage('CleanupFailed'), [Path]), mbError, MB_OK);
end;
procedure CurUninstallStepChanged(Step: TUninstallStep);
begin
  if Step = usPostUninstall then begin
    RegDeleteValue(HKCU, RunKey, 'YaMusicRPC');
    RegDeleteValue(HKCU, RunKey, 'WinYandexMusicRPC');
    DeleteFile(ExpandConstant('{userstartup}\YaMusicRPC.lnk'));
    DeleteFile(ExpandConstant('{userstartup}\WinYandexMusicRPC.lnk'));
    RemoveDataFolder(ExpandConstant('{localappdata}\WinYandexMusicRPC'));
    RemoveDataFolder(ExpandConstant('{userappdata}\WinYandexMusicRPC'));
  end;
end;

