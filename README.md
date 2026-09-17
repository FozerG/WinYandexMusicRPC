# <img src="./assets/YMRPC_ico.ico" alt="[DISCORD STATUS]" width="30"/> &nbsp;WinYandexMusicRPC — Музыка в статусе Discord из любого приложения
[![TotalDownloads](https://img.shields.io/github/downloads/FozerG/WinYandexMusicRPC/total)](https://github.com/FozerG/WinYandexMusicRPC/releases "Download") [![LastRelease](https://img.shields.io/github/v/release/FozerG/WinYandexMusicRPC)](https://github.com/FozerG/WinYandexMusicRPC/releases "Download") [![CodeOpen](https://img.shields.io/github/languages/top/FozerG/WinYandexMusicRPC)](https://github.com/FozerG/WinYandexMusicRPC/blob/main/main.py "Show code") [![OS - Windows](https://img.shields.io/badge/OS-Windows-blue?logo=windows&logoColor=white)](https://github.com/FozerG/WinYandexMusicRPC/releases "Download")

>Несмотря на неразумное решение о блокировке Discord в РФ, я продолжу поддерживать скрипт в рабочем состоянии, насколько это будет возможно 🕊️

>[Мы будем пользоваться тем, что нам нравится.](https://github.com/Flowseal/zapret-discord-youtube)

**Программа показывает музыку в статусе Discord из Яндекс Музыки, Spotify, Apple Music, браузеров и других приложений, которые передают медиаданные Windows.**

**Режим Ynison позволяет отображать музыку из Яндекс Музыки, которая сейчас воспроизводится на мобильном устройстве.**

<img src="https://github.com/user-attachments/assets/e2741c91-565a-480e-92af-4aae95332fcb" alt="discord" width="340">

## О программе

WinYandexMusicRPC появился в 2023 году как небольшой личный проект для отображения музыки из Яндекс Музыки в Discord. Со временем он вырос в универсальную программу для музыкального статуса Discord.

Программа получает данные о воспроизведении из Windows или напрямую из аккаунта Яндекс Музыки и публикует статус «Слушает» в Discord.

## Возможности

- ✅ Статус «Слушает» в Discord
- ✅ Поддержка Яндекс Музыки, Spotify, Apple Music, ВКонтакте, браузеров и других приложений
- ✅ Треки из подборок, радио и «Моей Волны»
- ✅ Поиск через Яндекс Музыку, iTunes и Deezer
- ✅ Обложка, альбом и ссылки на трек
- ✅ Прогресс и время до конца трека
- ✅ Статус паузы и настраиваемое отключение
- ✅ Отображение подкастов и загруженных треков в Яндекс Музыку
- ✅ Показывает музыку с мобильных устройств через режим Ynison
- ✅ Работа в трее и автозапуск Windows

## Скачивание и запуск

Программа работает только на Windows 10 и Windows 11. Работа на Lite, Custom и других изменённых сборках Windows не гарантируется.

1. Скачайте [последний релиз](https://github.com/FozerG/WinYandexMusicRPC/releases).
2. Запустите установщик `WinYandexMusicRPC_Installer.exe`.
3. Запустите ярлык **WinYandexMusicRPC** с рабочего стола.
4. Настройте источник музыки и статус Discord в открывшемся окне.

После закрытия окна программа продолжит работать в системном трее. Через значок в трее можно открыть настройки, посмотреть журнал или полностью завершить программу.

<details>
<summary><b>Запуск из исходного кода</b></summary>

Для запуска нужен Python **3.11–3.14** и Git.

1. Откройте терминал в папке, где находятся `requirements.txt` и `main.py`.

2. Создайте виртуальное окружение:

```powershell
python -m venv .venv
```

3. Установите зависимости:

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

4. Запустите программу:

```powershell
.venv\Scripts\python main.py
```

Настройки можно открыть через значок программы в системном трее или командой:

```powershell
.venv\Scripts\python main.py --show-settings
```

## Сборка EXE

1. Установите PyInstaller:

```powershell
.venv\Scripts\python -m pip install pyinstaller
```

2. Выполните сборку:

```powershell
.venv\Scripts\python -m PyInstaller --noconfirm main.spec
```

Готовая программа находится в папке `dist/WinYandexMusicRPC-gui`. Для работы нужны `WinYandexMusicRPC.exe` и папка `_internal` рядом с ним.

</details>

------------

## Баги
Баги всегда существуют, но сначала их надо найти 🫡  
Если вы нашли ошибку, то не стесняйтесь сообщать о ней в [Issues](https://github.com/FozerG/WinYandexMusicRPC/issues)
   
------------
Пожалуйста, покажите вашу заинтересованность в этом проекте, что бы я мог его обновлять по мере возможности.

> Часть кода и рефакторинг исходной версии проекта 2023 года были выполнены с помощью AI. Старый код требовал серьёзной переработки, поэтому AI использовался как инструмент для улучшения структуры, поддержки и развития программы.
