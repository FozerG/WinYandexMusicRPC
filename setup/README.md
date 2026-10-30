## Сборка установщика

Нужен **Inno Setup 7.1.1**. Сначала соберите приложение по [основной инструкции](../README.md).

Из корня проекта:

```powershell
powershell -ExecutionPolicy Bypass -File setup/build.ps1
```

Результат: `dist/WinYandexMusicRPC_Setup_<версия>.exe`. Версия берётся из `pyproject.toml`.
Путь к компилятору можно передать через `-Compiler`.
