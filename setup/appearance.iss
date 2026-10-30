var
  IsUpdate: Boolean;

procedure InitializeWizard;
var
  Padding: Integer;
begin
  WizardForm.MainPanel.StyleElements := [seFont, seBorder];
  WizardForm.MainPanel.ParentBackground := False;
  WizardForm.MainPanel.Color := $202020;
  with WizardForm.WizardSmallBitmapImage do begin
    Padding := Width div 8;
    SetBounds(Left + Padding, Top + Padding, Width - 2 * Padding, Height - 2 * Padding);
  end;
end;

function NextButtonClick(PageID: Integer): Boolean;
var
  Entry: TFindRec;
begin
  Result := True;
  if PageID = wpSelectDir then begin
    IsUpdate := FileExists(AddBackslash(WizardDirValue) + 'WinYandexMusicRPC.exe');
    if not IsUpdate then
      if FindFirst(AddBackslash(WizardDirValue) + '*', Entry) then begin
        try
          repeat
            if (Entry.Name <> '.') and (Entry.Name <> '..') then Result := False;
          until not FindNext(Entry);
        finally
          FindClose(Entry);
        end;
        if not Result then MsgBox(CustomMessage('InvalidFolder'), mbError, MB_OK);
      end;
  end;
end;

procedure CurPageChanged(PageID: Integer);
begin
  if PageID = wpReady then begin
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);
    IsUpdate := FileExists(AddBackslash(WizardDirValue) + 'WinYandexMusicRPC.exe');
    if IsUpdate then begin
      WizardForm.NextButton.Caption := CustomMessage('UpdateButton');
      WizardForm.ReadyLabel.Caption := CustomMessage('UpdateHint');
    end;
  end else if (PageID = wpInstalling) and IsUpdate then begin
    WizardForm.PageNameLabel.Caption := CustomMessage('Update');
    WizardForm.PageDescriptionLabel.Caption := CustomMessage('WaitUpdate');
  end else if PageID = wpFinished then begin
    WizardForm.FinishedLabel.Caption := CustomMessage('DoneHint');
    WizardForm.FinishedLabel.Height := ScaleY(36);
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
  end;
end;
