from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from config_manager import ConfigManager
from itertools import permutations
from packaging import version
from datetime import timedelta
from yandex_music import Client, exceptions
from colorama import init, Fore, Style
from win32com.client import Dispatch  # Импортируем Dispatch для создания COM объекта


import multiprocessing
import subprocess
import webbrowser
import pystray
import win32gui
import win32con
import win32console
import threading
import pypresence
import getToken
import keyring
import requests
import asyncio
import psutil
import string
import json
import time
import re
import sys
import os
import winreg
import threading
import pythoncom
from enum import Enum
from PIL import Image
# Идентификатор клиента Discord для Rich Presence
CLIENT_ID_EN = '1269807014393942046' #Yandex Music
CLIENT_ID_RU = '1217562797999784007' #Яндекс Музыка
CLIENT_ID_RU_DECLINED = '1269826362399522849' #Яндекс Музыку (склонение для активности "Слушает")

# Версия (tag) скрипта для проверки на актуальность через Github Releases
CURRENT_VERSION = "v2.5.1"

# Ссылка на репозиторий
REPO_URL = "https://github.com/FozerG/WinYandexMusicRPC"

# (Опционально) Личный токен Яндекс.Музыки с подпиской Плюс (https://github.com/MarshalX/yandex-music-api/discussions/513)
# - Используется для поиска треков которые не показываются без авторизации
# - Используется при использовании скрипта из стран где бесплатная Яндекс.Музыка не работает
ya_token = str()

# Флаг для поиска трека с 100% совпадением названия и автора. Иначе будет найден близкий результат.
strong_find = True

# Флаг для настройки автозапуска с компьютером
auto_start_windows = False

# --------- Переменные ниже являются временными и не требуют изменения.
# Переменная для хранения предыдущего трека и избежания дублирования обновлений.
name_prev = str()

# Переменая для хранения полного пути к иконке
icoPath = str()

# Очередь для передачи результатов между процессами
result_queue = multiprocessing.Queue()

# Переменная для проверки необходимости запуска рестарта в главном потоке Presence
needRestart  = False

# Переменная для хранения иконки в трее
iconTray = True

# Переменная для хранения MediaManager.request_async что бы избежать лишних вызовов
media_sessions = None

#Менеджер настроек
config_manager = ConfigManager()

# Enum для конфигурации кнопок
class ButtonConfig(Enum):
    YANDEX_MUSIC_WEB = 1
    YANDEX_MUSIC_APP = 2
    BOTH = 3
    NEITHER = 4

# Enum для типа активности
class ActivityTypeConfig(Enum):
    PLAYING = 0
    LISTENING = 2

# Enum для выбора языка RPC
class LanguageConfig(Enum):
    ENGLISH = 0
    RUSSIAN = 1

# Глобальные настройки для RPC. Загружаются из метода get_saves_settings()
activityType_config = None
button_config = None
language_config = None

# Enum для статуса воспроизведения мультимедийного контента.
class PlaybackStatus(Enum):
    Unknown = 0
    Closed = 1
    Opened = 2
    Paused = 3
    Playing = 4
    Stopped = 5

# Функция для получения информации о мультимедийном контенте через Windows SDK
async def get_media_info():
    global media_sessions
    if media_sessions is None:
        try:
            log("Making the first request to windows MediaManager...", LogType.Default)
            media_sessions = await MediaManager.request_async()
        except Exception as e:
            log(f"Failed to get MediaManager sessions: {e}", LogType.Error)
            return None

    current_session = media_sessions.get_current_session()
    all_sessions = media_sessions.get_sessions()
    selected_session_id = config_manager.get_selected_session()
    target_session = None
    if selected_session_id and selected_session_id != "Automatic":
        # Пробуем найти сессию по source_app_user_model_id
        for session in all_sessions:
            if session.source_app_user_model_id == selected_session_id:
                target_session = session
                break

        if not target_session:
            raise Exception(f"Selected session '{selected_session_id}' not found.")
    else:
        target_session = media_sessions.get_current_session()

    if target_session:
        info = await target_session.try_get_media_properties_async()
        artist = info.artist
        title = info.title
        position = target_session.get_timeline_properties().position
        playback_info = target_session.get_playback_info()
        playback_status = PlaybackStatus(playback_info.playback_status).name
        session_title = info.title or "Unknown Title"
        app_name = target_session.source_app_user_model_id or "Unknown App"
        return {
            'artist': artist,
            'title': title,
            'playback_status': playback_status,
            'position': position,
            'session_title': session_title,
            'app_name': app_name
        }

    raise Exception('The music is not playing right now.')

async def get_session_ids():
    global media_sessions
    if media_sessions is None:
        try:
            log("Making the first request to windows MediaManager...", LogType.Default)
            media_sessions = await MediaManager.request_async()
        except Exception as e:
            log(f"Failed to get MediaManager sessions: {e}", LogType.Error)
            return None
    return [
        session.source_app_user_model_id or "UnknownApp"
        for session in media_sessions.get_sessions()
    ]

class Presence:
    client = None
    currentTrack = None
    rpc = None
    running = False
    paused = False
    paused_time = 0
    exe_names = ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe", "Vesktop.exe"]

    @staticmethod
    def is_discord_running() -> bool:
        return any(name in (p.name() for p in psutil.process_iter()) for name in Presence.exe_names)

    @staticmethod
    def connect_rpc():
        try:
            client_id = CLIENT_ID_EN if language_config == LanguageConfig.ENGLISH else \
                CLIENT_ID_RU_DECLINED if activityType_config == ActivityTypeConfig.LISTENING else CLIENT_ID_RU
            rpc = pypresence.Presence(client_id)
            rpc.connect()
            return rpc
        except pypresence.exceptions.DiscordNotFound:
            log("Pypresence - Discord not found.", LogType.Error)
            return None
        except pypresence.exceptions.InvalidID:
            log("Pypresence - Incorrect CLIENT_ID", LogType.Error)
            return None
        except Exception as e:
            log(f"Discord is not ready for a reason: {e}", LogType.Error)
            return None

    @staticmethod
    def discord_available() -> bool:
        while True:
            if Presence.is_discord_running():
                Presence.rpc = Presence.connect_rpc()
                if Presence.rpc:
                    log("Discord is ready for Rich Presence")
                    break
                else:
                    log("Discord is launched but not ready for Rich Presence. Try again...", LogType.Error)
            else:
                log("Discord is not launched", LogType.Error)
            time.sleep(3)

    @staticmethod
    def stop() -> None:
        if Presence.rpc:
            Presence.rpc.close()
            Presence.rpc = None
            Presence.running = False

    @staticmethod
    def need_restart() -> None:
        log("Restarting RPC because settings have been changed...", LogType.Update_Status)
        global needRestart
        needRestart = True

    @staticmethod
    def restart() -> None:
        Presence.currentTrack = None
        global name_prev
        name_prev = None
        if Presence.rpc:
            Presence.rpc.close()
            Presence.rpc = None
        time.sleep(3)
        Presence.discord_available()

    @staticmethod
    def discord_was_closed() -> None:
        log("Discord was closed. Waiting for restart...", LogType.Error)
        Presence.currentTrack = None
        global name_prev
        name_prev = None
        Presence.discord_available()

    # Метод для запуска Rich Presence.
    @staticmethod
    def start() -> None:
        global ya_token
        global needRestart
        Presence.discord_available()
        if Presence.client:
            log("Initialize client with token...", LogType.Default)
        else:
            Presence.client = Client().init()
        Presence.running = True
        Presence.currentTrack = None
        while Presence.running:
            currentTime = time.time()
            if not Presence.is_discord_running():
                Presence.discord_was_closed()
            if needRestart:
                needRestart = False
                Presence.restart()
            try:
                ongoing_track = Presence.getTrack()
                if Presence.currentTrack != ongoing_track: # проверяем что песня не играла до этого, т.к она просто может быть снята с паузы.
                    if ongoing_track['success']:
                        if Presence.currentTrack is not None and 'label' in Presence.currentTrack and Presence.currentTrack['label'] is not None:
                            if ongoing_track['label'] != Presence.currentTrack['label']:
                                log(f"Changed track to {ongoing_track['label']}", LogType.Update_Status)
                        else:
                            log(f"Changed track to {ongoing_track['label']}", LogType.Update_Status)
                        Presence.paused_time = 0
                        trackTime = currentTime
                        start_time = currentTime - int(ongoing_track['start-time'].total_seconds())
                        end_time = start_time + ongoing_track['durationSec']
                        presence_args = {
                            'activity_type': activityType_config.value,
                            'details': ongoing_track['title'],
                            'state': ongoing_track['artist'],
                            'start': start_time,
                            'end': end_time,
                            'large_image': ongoing_track['og-image'],
                        }

                        if ongoing_track['album'] != ongoing_track['title']:
                            presence_args['large_text'] = ongoing_track['album']

                        if button_config != ButtonConfig.NEITHER:
                            presence_args['buttons'] = build_buttons(ongoing_track['link'])

                        if activityType_config == ActivityTypeConfig.LISTENING:
                            presence_args['small_image'] = "https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Playing.png"
                            presence_args['small_text'] = "Playing" if language_config == LanguageConfig.ENGLISH else "Проигрывается"


                        Presence.rpc.update(**presence_args)
                    else:
                        Presence.rpc.clear()
                        log(f"Clear RPC")

                    Presence.currentTrack = ongoing_track

                else: #Песня не новая, проверяем статус паузы
                    if ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and not Presence.paused:
                        Presence.paused = True
                        log(f"Track {ongoing_track['label']} on pause", LogType.Update_Status)
                        if ongoing_track['success']:
                            presence_args = {
                                'activity_type': activityType_config.value,
                                'details': ongoing_track['title'],
                                'state': ongoing_track['artist'],
                                'large_image': ongoing_track['og-image'],
                                'large_text': ongoing_track['album'],
                                'small_image': "https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Paused.png",
                                'small_text': "On pause" if language_config == LanguageConfig.ENGLISH else "На паузе"
                            }
                            if button_config != ButtonConfig.NEITHER:
                                presence_args['buttons'] = build_buttons(ongoing_track['link'])

                            if activityType_config == ActivityTypeConfig.LISTENING and int(ongoing_track['start-time'].total_seconds()) != 0:
                                presence_args['large_text'] = f"{'On pause' if language_config == LanguageConfig.ENGLISH else 'На паузе'} {format_duration(int(ongoing_track['start-time'].total_seconds() * 1000))} / {ongoing_track['formatted_duration']}"
                            if int(ongoing_track['start-time'].total_seconds()) != 0:
                                presence_args['small_text'] = f"{'On pause' if language_config == LanguageConfig.ENGLISH else 'На паузе'} {format_duration(int(ongoing_track['start-time'].total_seconds() * 1000))} / {ongoing_track['formatted_duration']}"

                            Presence.rpc.update(**presence_args)

                    elif ongoing_track['success'] and ongoing_track["playback"] == PlaybackStatus.Playing.name and Presence.paused:
                        log(f"Track {ongoing_track['label']} off pause.", LogType.Update_Status)
                        Presence.paused = False

                    elif ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and Presence.paused and trackTime != 0:
                        Presence.paused_time = currentTime - trackTime
                        if Presence.paused_time > 5 * 60:  # если пауза больше 5 минут
                            trackTime = 0
                            Presence.rpc.clear()
                            log(f"Clear RPC due to paused for more than 5 minutes", LogType.Update_Status)
                    else:
                        Presence.paused_time = 0  # если трек продолжает играть, сбрасываем paused_time

                time.sleep(3)
            except pypresence.exceptions.PipeClosed:
                Presence.discord_was_closed()
            except Exception as e:
                log(f"Presence class stopped for a reason: {e}", LogType.Error)

    # Метод для получения информации о текущем треке.
    @staticmethod
    def getTrack() -> dict:
        global name_prev, strong_find
        try:
            current_media_info = run_async(get_media_info(), timeout=10)

            if not current_media_info:
                log("No media information returned from get_media_info", LogType.Error)
                return {'success': False}
            artist = current_media_info.get("artist", "").strip()
            title = current_media_info.get("title", "").strip()
            position = current_media_info['position']
            if not artist or not title:
                log(f"MediaManager returned empty string for artist or title. Active app - {current_media_info['app_name']}. Title - {current_media_info['session_title']}", LogType.Error)
                return {'success': False}
            name_current = artist + " - " + title
            if str(name_current) != name_prev:
                log("Now listening to " + name_current)
            else: #Если песня уже играет, то не нужно ее искать повторно. Просто вернем её с актуальным статусом паузы и позиции.
                currentTrack_copy = Presence.currentTrack.copy()
                currentTrack_copy["start-time"] = position
                currentTrack_copy["playback"] = current_media_info['playback_status']
                return currentTrack_copy

            name_prev = str(name_current)
            # Первая попытка — без апострофа
            search = Presence.client.search(name_current.replace("'", " "), True, "all", 0, False)

            # Если не нашли — вторая попытка с оригинальным именем
            if search.tracks is None:
                search = Presence.client.search(name_current, True, "all", 0, False)
            if search.tracks is None:
                log(f"Can't find the song: {name_current}")
                return {'success': False}

            finalTrack = None
            debugStr = []
            for index, trackFromSearch in enumerate(search.tracks.results[:5], start=1): #Из поиска проверяем первые 5 результатов
                if trackFromSearch.type not in ['music', 'track', 'podcast_episode']:
                    debugStr.append(f"[WinYandexMusicRPC] -> The result #{index} has the wrong type.")

                # Авторы могут отличатся положением, поэтому делаем все возможные варианты их порядка.
                artists = trackFromSearch.artists_name()
                if len(artists) <= 4:
                    all_variants = [list(variant) for variant in permutations(artists)]
                    findTrackNames = []
                    for variant in all_variants:
                        findTrackNames.append(', '.join([str(elem) for elem in variant]) + " - " + trackFromSearch.title)
                else:
                    findTrackNames = []
                    findTrackNames.append(', '.join(artists) + " - " + trackFromSearch.title)

                # Также может отличаться регистр, так что приведём всё в один регистр.
                boolNameCorrect = any(name_current.lower() == element.lower() for element in findTrackNames)

                if strong_find and not boolNameCorrect: #если strong_find и название трека не совпадает, продолжаем поиск
                    findTrackName = ', '.join([str(elem) for elem in trackFromSearch.artists_name()]) + " - " + trackFromSearch.title
                    debugStr.append(f"[WinYandexMusicRPC] -> The result #{index} has the wrong title. Now play: {name_current}. But we find: {findTrackName}")
                    continue
                else: #иначе трек найден
                    finalTrack = trackFromSearch
                    break

            if finalTrack is None:
                print('\n'.join(debugStr))
                log(f"Can't find the song (strong_find): {name_current}")
                return {'success': False}

            track = finalTrack
            trackId = track.trackId.split(":")
            if track:
                return {
                    'success': True,
                    'title': Single_char(TrimString(track.title, 40)),
                    'artist': Single_char(TrimString(f"{', '.join(track.artists_name())}",40)),
                    'album':    Single_char(TrimString(track.albums[0].title,25)),
                    'label': TrimString(f"{', '.join(track.artists_name())} - {track.title}",50),
                    'link': f"https://music.yandex.ru/album/{trackId[1]}/track/{trackId[0]}/",
                    'durationSec': track.duration_ms // 1000,
                    'formatted_duration': format_duration(track.duration_ms),
                    'start-time': position,
                    'playback': current_media_info['playback_status'],
                    'og-image': "https://" + track.og_image[:-2] + "400x400"
                }
        except asyncio.TimeoutError:
            log("Timeout: get_media_info() took more than 10 seconds", LogType.Error)
        except Exception as exception:
            Handle_exception(exception)
            return {'success': False}

def format_duration(duration_ms):
    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    # Форматирование строки
    return f"{minutes}:{seconds:02}"

# ВНИМАНИЕ!
# ДЛЯ ТЕКСТА КНОПКИ ЕСТЬ ОГРАНИЧЕНИЕ В 32 БАЙТА. КИРИЛЛИЦА СЧИТАЕТСЯ ЗА 2 БАЙТА.
# ЕСЛИ ПРЕВЫСИТЬ ЛИМИТ ТО DISCORD RPC НЕ БУДЕТ ВИДЕН ДРУГИМ ПОЛЬЗОВАТЕЛЯМ!
def build_buttons(url):
    buttons = []
    if button_config == ButtonConfig.YANDEX_MUSIC_WEB:
        buttons.append({'label': 'Listen on Yandex Music' if language_config == LanguageConfig.ENGLISH else 'Откр. в браузере', 'url': url})
    elif button_config == ButtonConfig.YANDEX_MUSIC_APP:
        deep_link = extract_deep_link(url)
        buttons.append({'label': 'Listen on Yandex Music (in App)' if language_config == LanguageConfig.ENGLISH else 'Откр. в прилож.', 'url': deep_link})
    elif button_config == ButtonConfig.BOTH:
        buttons.append({'label': 'Listen on Yandex Music (Web)' if language_config == LanguageConfig.ENGLISH else 'Откр. в браузере', 'url': url})
        deep_link = extract_deep_link(url)
        buttons.append({'label': 'Listen on Yandex Music (App)' if language_config == LanguageConfig.ENGLISH else 'Откр. в прилож.', 'url': deep_link})

    for button in buttons:
        label = button['label']
        if len(label.encode('utf-8')) > 32:
            raise ValueError(f"Label '{label}' exceeds 32 bytes")
    return buttons

def extract_deep_link(url):
    pattern = r"https://music.yandex.ru/album/(\d+)/track/(\d+)"
    match = re.match(pattern, url)

    if match:
        album_id, track_id = match.groups()
        share_track_path = f"album/{album_id}/track/{track_id}"
        deep_share_track_url = "yandexmusic://" + share_track_path
        return deep_share_track_url
    else:
        return None

def Handle_exception(exception): # Обработка json ошибок из Yandex Music
    json_str = str(exception).replace("'", '"')
    match = re.search(r'({.*?})', json_str)
    if match:
        json_str = match.group(1)

    try:
        data = json.loads(json_str)
        error_name = data.get('name')
        if error_name:
            if error_name == 'Unavailable For Legal Reasons':
                log("You are using Yandex music in a country where it is not available without authorization! Turn off VPN or login using a Yandex token.", LogType.Error)
            elif error_name == 'session-expired':
                log("Your Yandex token is out of date or incorrect, login again.", LogType.Error)
            else:
                log(f"Something happened: {exception}", LogType.Error)
        else:
            log(f"Something happened: {exception}", LogType.Error)
    except Exception:
        log(f"Something happened: {exception}", LogType.Error)

def WaitAndExit():
    if Is_run_by_exe():
        win32gui.ShowWindow(window, win32con.SW_SHOW)
    Presence.stop()
    input("Press Enter to close the program.\n")
    if Is_run_by_exe():
        win32gui.PostMessage(window, win32con.WM_CLOSE, 0, 0)
    else:
        sys.exit(0)

def TrimString(string, maxChars):
    if len(string) > maxChars:
        return string[:maxChars] + "..."
    else:
        return string

def Single_char(s):
    if len(s) == 1:
        return f'"{s}"'
    return s

class LogType(Enum):
    Default = 0
    Notification = 1
    Error = 2
    Update_Status = 3

def log(text, type = LogType.Default):
    init() #Инициализация colorama
    # Цвета текста
    red_text = Fore.RED
    yellow_text = Fore.YELLOW
    blue_text = Fore.CYAN
    reset_text = Style.RESET_ALL

    if type == LogType.Notification:
        message_color = yellow_text
    elif type == LogType.Error:
        message_color = red_text
    elif type == LogType.Update_Status:
        message_color = blue_text
    else:
        message_color = reset_text

    print(f"{red_text}[WinYandexMusicRPC] -> {message_color}{text}{reset_text}")


def GetLastVersion(repoUrl):
    try:
        global CURRENT_VERSION
        response = requests.get(repoUrl + '/releases/latest', timeout=5)
        response.raise_for_status()
        latest_version = response.url.split('/')[-1]

        if version.parse(CURRENT_VERSION) < version.parse(latest_version):
            log(f"A new version has been released on GitHub. You are using - {CURRENT_VERSION}. A new version - {latest_version}, you can download it at {repoUrl + '/releases/tag/' + latest_version}", LogType.Notification)
        elif version.parse(CURRENT_VERSION) == version.parse(latest_version):
            log(f"You are using the latest version of the script")
        else:
            log(f"You are using the beta version of the script", LogType.Notification)

    except requests.exceptions.RequestException as e:
        log(f"Error getting latest version: {e}", LogType.Error)


# Функция для переключения состояния strong_find
def toggle_strong_find():
    global strong_find
    strong_find = not strong_find
    config_manager.set_setting('UserSettings', 'strong_find', str(strong_find))  # Сохраняем новое значение
    log(f'Bool strong_find set state: {strong_find}')

# Функция для переключения состояния auto_start_windows
def toggle_auto_start_windows():
    global auto_start_windows
    auto_start_windows = not auto_start_windows
    log(f'Bool auto_start_windows set state: {auto_start_windows}')

    def create_shortcut(target, shortcut_path, description="", arguments=""):
        pythoncom.CoInitialize()  # Инициализируем COM библиотеки
        shell = Dispatch('WScript.Shell')  # Создаем объект для работы с ярлыками
        shortcut = shell.CreateShortcut(shortcut_path)  # Создаем ярлык
        shortcut.TargetPath = target  # Устанавливаем путь к исполняемому файлу
        shortcut.WorkingDirectory = os.path.dirname(target)  # Устанавливаем рабочую директорию
        shortcut.Description = description  # Устанавливаем описание ярлыка
        shortcut.Arguments = arguments
        shortcut.Save()  # Сохраняем ярлык

    def change_setting(tglle: bool): # Выношу в отдельную функцию, чтобы иметь возможность запустить в отдельном потоке,
        if tglle:# ДВА способа добавления в автозапуск. Первый через добавление программы в папку автостарта. Второй через изменение реестра. Оба не требуют админских прав.
            try: # Автозапуск через добавление в папку автозапуска
                exe_path = os.path.abspath(sys.argv[0])  # Получаем абсолютный путь к текущему исполняемому файлу
                shortcut_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'YaMusicRPC.lnk')  # Определяем путь для ярлыка в автозагрузке
                create_shortcut(exe_path, shortcut_path, arguments="--run-through-startup")  # Создаем ярлык в автозагрузке
            except: # Автозапуск через изменение в реестре
                exe_path = f'"{os.path.abspath(sys.argv[0])}" --run-through-startup'
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_SET_VALUE)  # Открываем ключ реестра для автозапуска программ
                winreg.SetValueEx(key, 'YaMusicRPC', 0, winreg.REG_SZ, exe_path)  # Устанавливаем новый параметр в реестре с именем 'YaMusicRPC' и значением пути к исполняемому файлу
                winreg.CloseKey(key)  # Закрываем ключ реестра
        else: # Удаляем оба метода
            # Удаляем ярлык из автозагрузки
            shortcut_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'YaMusicRPC.lnk')
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
            # Удаляем запись из реестра
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_ALL_ACCESS)
                winreg.DeleteValue(key, 'YaMusicRPC')
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass


    threading.Thread(target=change_setting, args=[auto_start_windows]).start() # Запускаем в отдельном потоке для оптимизации

def is_in_autostart(): # Функция, которая при запуске программы проверяет, есть ли программа в автозапуске. Используется при подгрузке стартовых параметров

    def is_in_startup():
        shortcut_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'YaMusicRPC.lnk')  # Определяем путь к ярлыку
        return os.path.exists(shortcut_path)  # Проверяем, существует ли ярлык в папке автозагрузки

    def is_in_registry():
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)  # Открываем ключ реестра для чтения
            winreg.QueryValueEx(key, 'YaMusicRPC')  # Проверяем, существует ли параметр в реестре
            winreg.CloseKey(key)  # Закрываем ключ реестра
            return True
        except FileNotFoundError:
            return False  # Если параметр не найден, возвращаем False

    return is_in_startup() or is_in_registry()  # Возвращаем True, если программа присутствует в автозапуске


def toggle_console():
    if win32gui.IsWindowVisible(window):
        win32gui.ShowWindow(window, win32con.SW_HIDE)
    else:
        Show_Console_Permanent()

# Действия для кнопок
def tray_click(icon, query):
    match str(query):
        case "GitHub":
            webbrowser.open(REPO_URL,  new=2)

        case "Exit":
            Presence.stop()
            icon.stop()
            win32gui.PostMessage(window, win32con.WM_CLOSE, 0, 0)

def get_account_name():
    try:
        user_info = Presence.client.me.account
        account_name = user_info.display_name
        if not account_name:
            return f"None"
        return account_name
    except exceptions.UnauthorizedError:
        return "Invalid token."

    except exceptions.NetworkError:
        return "Network error."

    except Exception as e:
        return f"None"

# Функция для загрузки сохраненных настроек. Если настройки отсутствуют, используются значения по умолчанию из fallback.
def get_saves_settings(fromStart = False):
    global activityType_config
    global button_config
    global language_config
    global auto_start_windows
    global strong_find

    auto_start_windows = is_in_autostart()
    activityType_config = config_manager.get_enum_setting('UserSettings', 'activity_type', ActivityTypeConfig, fallback=ActivityTypeConfig.LISTENING)
    button_config = config_manager.get_enum_setting('UserSettings', 'buttons_settings', ButtonConfig, fallback=ButtonConfig.BOTH)
    language_config = config_manager.get_enum_setting('UserSettings', 'language', LanguageConfig, fallback=LanguageConfig.RUSSIAN)

    # Загрузка значения strong_find из конфигурации
    strong_find_str = config_manager.get_setting('UserSettings', 'strong_find', fallback='True')  # По умолчанию 'True'
    strong_find = strong_find_str.lower() == 'true'  # Преобразуем строку в булевое значение

    if fromStart:
        log(f"Loaded settings: {Style.RESET_ALL}activityType_config = {activityType_config.name}, button_config = {button_config.name}, language_config = {language_config.name}, strong_find = {strong_find}, selected_session = {config_manager.get_selected_session()}", LogType.Update_Status)

def run_async(coro, timeout=15):
    """
    Безопасно запускает асинхронную корутину из синхронного контекста.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    else:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

def create_session_toggle_menu(icon):
    try:
        session_ids = run_async(get_session_ids(), timeout=10)
    except Exception as e:
        log(f"Failed to get session IDs for tray menu: {e}", LogType.Error)
        session_ids = []

    menu_items = []

    # Кнопка обновления
    menu_items.append(
        pystray.MenuItem(
            'Update List',
            lambda item: update_tray()
        )
    )

    menu_items.append(pystray.Menu.SEPARATOR)

    selected_session = config_manager.get_selected_session()
    session_ids_set = set(session_ids)

    def set_automatic(item):
        log("Selected session: Automatic", LogType.Default)
        config_manager.set_selected_session("Automatic")

    def is_automatic(item):
        return config_manager.get_selected_session() == "Automatic"

    menu_items.append(
        pystray.MenuItem(
            "Automatic",
            set_automatic,
            checked=is_automatic,
            radio=True
        )
    )

    # Добавляем активные сессии
    for session_id in session_ids:
        def make_action(sid):
            def action(item):
                log(f"Selected session: {sid}", LogType.Default)
                config_manager.set_selected_session(sid)
            return action

        def make_checked(sid):
            return lambda item: config_manager.get_selected_session() == sid

        menu_items.append(
            pystray.MenuItem(
                session_id,
                make_action(session_id),
                checked=make_checked(session_id),
                radio=True
            )
        )

    # Если сохранённая сессия отсутствует в текущем списке - добавить её как "inactive"
    if selected_session and selected_session not in session_ids_set and selected_session != "Automatic":
        def make_action_inactive():
            return lambda item: config_manager.set_selected_session(selected_session)

        def make_checked_inactive():
            return lambda item: config_manager.get_selected_session() == selected_session

        menu_items.append(
            pystray.MenuItem(
                f"{selected_session} (inactive)",
                make_action_inactive(),
                checked=make_checked_inactive(),
                radio=True
            )
        )

    return pystray.Menu(*menu_items)


# Функция для создания меню на основе переданных параметров
def create_enum_menu(enum_class, get_setting_func, set_setting_func):
    return pystray.Menu(
        *(pystray.MenuItem(value.name,
                           lambda item, value=value: set_setting_func(value),
                           checked=lambda item, value=value: get_setting_func('UserSettings', enum_class) == value)
          for value in enum_class)
    )

def convert_to_enum(enum_class, value):
    value_str = str(value)
    try:
        return enum_class[value_str]
    except KeyError:
        log(f"Invalid type: {value_str}")
        return None

# Функции для установки значений
def set_activity_type(value):
    value = convert_to_enum(ActivityTypeConfig, value)
    config_manager.set_enum_setting('UserSettings', 'activity_type', value)
    log(f"Setting has been changed : activity_type to {value.name}")
    get_saves_settings()
    Presence.need_restart()

def set_button_config(value):
    value = convert_to_enum(ButtonConfig, value)
    config_manager.set_enum_setting('UserSettings', 'buttons_settings', value)
    log(f"Setting has been changed : buttons_settings to {value.name}")
    get_saves_settings()
    Presence.need_restart()

def set_language_config(value):
    value = convert_to_enum(LanguageConfig, value)
    config_manager.set_enum_setting('UserSettings', 'language', value)
    log(f"Setting has been changed : language to {value.name}")
    get_saves_settings()
    Presence.need_restart()

# Функция для создания настроек меню RPC
def create_rpc_settings_menu():
    activity_type_menu = create_enum_menu(ActivityTypeConfig, lambda section, enum_type: config_manager.get_enum_setting(section, 'activity_type', enum_type), set_activity_type)
    button_config_menu = create_enum_menu(ButtonConfig, lambda section, enum_type: config_manager.get_enum_setting(section, 'buttons_settings', enum_type), set_button_config)
    language_config_menu = create_enum_menu(LanguageConfig, lambda section, enum_type: config_manager.get_enum_setting(section, 'language', enum_type), set_language_config)

    return pystray.Menu(
        pystray.MenuItem('Activity Type', activity_type_menu),
        pystray.MenuItem('RPC Buttons', button_config_menu),
        pystray.MenuItem("RPC Language", language_config_menu),
    )

# Функция для создания иконки с меню
def build_tray_menu(icon=None):
    account_name = get_account_name()
    rpcSettingsMenu = create_rpc_settings_menu()

    settingsMenu = pystray.Menu(
        pystray.MenuItem(f"Logged in as - {account_name}", lambda: None, enabled=False),
        pystray.MenuItem('Login to account...', lambda: Init_yaToken(True)),
        pystray.MenuItem('Toggle strong_find', toggle_strong_find, checked=lambda item: strong_find),
    )

    return pystray.Menu(
        pystray.MenuItem("Hide/Show Console", toggle_console, default=True),
        pystray.MenuItem('Start with Windows', toggle_auto_start_windows, checked=lambda item: auto_start_windows),
        pystray.MenuItem("Yandex settings", settingsMenu),
        pystray.MenuItem("RPC settings", rpcSettingsMenu),
        pystray.MenuItem("Select Application", create_session_toggle_menu(icon) if icon else pystray.MenuItem("Loading...", lambda: None, enabled=False)),
        pystray.MenuItem("GitHub", tray_click),
        pystray.MenuItem("Exit", tray_click)
    )

def update_tray():
    global iconTray
    if iconTray is not None:
        iconTray.menu = build_tray_menu(iconTray)

# Функция для запуска иконки
def tray_thread(initial_menu):
    global iconTray
    tray_image = Image.open(Get_IconPath())
    icon = pystray.Icon("WinYandexMusicRPC", tray_image, "WinYandexMusicRPC", menu=initial_menu)
    iconTray = icon

    icon.run_detached()
    update_tray()

def Is_already_running():
    hwnd = win32gui.FindWindow(None, "WinYandexMusicRPC - Console")
    if hwnd:
        return True
    return False

def Is_windows_11():
    return sys.getwindowsversion().build >= 22000


def Check_conhost():
    if Is_windows_11():  # Windows 11 имеет консоль, которую нельзя свернуть в трей, поэтому мы используем conhost
        if '--run-through-conhost' not in sys.argv:  # Запущен ли скрипт уже через conhost
            Run_by_startup_without_conhost()
            print("Wait a few seconds for the script to load...")
            script_path = os.path.abspath(sys.argv[0])
            first_pid = os.getpid()
            subprocess.Popen(['start', '/min', 'conhost.exe', script_path, '--run-through-conhost', str(first_pid)] + sys.argv[1:], shell=True)
            event = threading.Event()
            event.wait()

    if '--run-through-launcher' in sys.argv or '--run-through-conhost' in sys.argv:  # Запущен ли скрипт уже через conhost или лаунчер
        if len(sys.argv) > 2:
            first_pid = int(sys.argv[2])
            try:
                parent_process = psutil.Process(first_pid)
                for child in parent_process.children(recursive=True):
                    child.terminate()
                parent_process.terminate()
                parent_process.wait(timeout=3)
            except Exception:
                print(f"Couldnt close the process: {first_pid}")

def Show_Console_Permanent():
    try:
        win32gui.ShowWindow(window, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(window)
    except Exception as e:
        log(f"We cant show the window {e}",LogType.Error)

def Check_run_by_startup():
    # Если приложение запущено через автозагрузку, скрываем окно консоли сразу.
    # Если приложение запущено вручную, показываем окно консоли на 3 секунды и затем сворачиваем.
    if window:
        if '--run-through-startup' not in sys.argv:
            Show_Console_Permanent()
            log("Minimize to system tray in 3 seconds...")
            time.sleep(3)
        win32gui.ShowWindow(window, win32con.SW_HIDE)
    else:
        log("Console window not found", LogType.Error)

def Run_by_startup_without_conhost():
    # Функция для автозагрузки без лаунчера (Windows 11), скрывает окно консоли при запуске через автозагрузку.
    window = win32console.GetConsoleWindow()
    if window:
        if '--run-through-startup' in sys.argv:
            win32gui.ShowWindow(window, win32con.SW_HIDE)
    else:
        log("Console window not found", LogType.Error)

def Disable_close_button():
    hwnd = win32console.GetConsoleWindow()
    if hwnd:
        hMenu = win32gui.GetSystemMenu(hwnd, False)
        if hMenu:
            win32gui.DeleteMenu(hMenu, win32con.SC_CLOSE, win32con.MF_BYCOMMAND)

def Set_ConsoleMode():
    hStdin = win32console.GetStdHandle(win32console.STD_INPUT_HANDLE)
    mode = hStdin.GetConsoleMode()
    # Отключить ENABLE_QUICK_EDIT_MODE, чтобы запретить выделение текста
    new_mode = mode & ~0x0040
    hStdin.SetConsoleMode(new_mode)

def Is_run_by_exe():
    script_path = os.path.abspath(sys.argv[0])
    if script_path.endswith('.exe'):
        return True
    else:
        return False

def Blur_string(s: str) -> str:
    if s is None:
        return ''
    if len(s) <= 8:
        return s
    return s[:4] + '*' * (len(s) - 8) + s[-4:]

def Remove_yaToken_From_Memmory():
    if keyring.get_password('WinYandexMusicRPC', 'token') is not None:
        keyring.delete_password('WinYandexMusicRPC', 'token')
        log("Old token has been removed from memory.", LogType.Update_Status)

def update_token_task(icon_path, result_queue):
    result = getToken.get_yandex_music_token(icon_path)
    result_queue.put(result)

def Init_yaToken(forceGet = False):
    global ya_token
    token = str()

    if forceGet:
        try:
            Remove_yaToken_From_Memmory()
            process = multiprocessing.Process(target=update_token_task, args=(Get_IconPath(), result_queue))
            process.start()
            process.join()
            token = result_queue.get()
            if token is not None and len(token) > 10:
                keyring.set_password('WinYandexMusicRPC', 'token', token)
                log(f"Successfully received the token: {Blur_string(token)}", LogType.Update_Status)
        except Exception as exception:
            log(f"Something happened when trying to initialize token: {exception}", LogType.Error)
    else:
        if not ya_token:
            try:
                token = keyring.get_password('WinYandexMusicRPC', 'token')
                if token:
                    log(f"Loaded token: {Blur_string(token)}", LogType.Update_Status)
            except Exception as exception:
                log(f"Something happened when trying to initialize token: {exception}", LogType.Error)
        else:
            token = ya_token
            log(f"Loaded token from script: {Blur_string(token)}", LogType.Update_Status)

    if token is not None and len(token) > 10:
        ya_token = token
        try:
            Presence.client = Client(token=ya_token).init()
            log(f"Logged in as - {get_account_name()}", LogType.Update_Status)
            if Is_run_by_exe():
                update_tray()
        except Exception as exception:
            Handle_exception(exception)
    if not Presence.client:
        log("Continue without a token...", LogType.Default)



def Get_IconPath():
    try:
        # Установка пути к ресурсам
        if getattr(sys, 'frozen', False):  # Запуск с помощью PyInstaller
            resources_path = sys._MEIPASS
        else:
            resources_path = os.path.dirname(os.path.abspath(__file__))

        return f"{resources_path}/assets/YMRPC_ico.ico"
    except Exception:
        return None



if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        if Is_run_by_exe():
            Check_conhost()
            Set_ConsoleMode()
            log("Launched. Check the actual version...")
            GetLastVersion(REPO_URL)
            # Загрузка настроек
            get_saves_settings(True)
            # Запуск потока для трея
            mainMenu = build_tray_menu()
            icon_thread = threading.Thread(target=tray_thread, args=(mainMenu,))
            icon_thread.daemon = True
            icon_thread.start()

            # Получение окна консоли
            window = win32console.GetConsoleWindow()

            if Is_already_running():
                log("WinYandexMusicRPC is already running.", LogType.Error)
                Show_Console_Permanent()
                WaitAndExit()

            # Установка заголовка окна консоли
            win32console.SetConsoleTitle("WinYandexMusicRPC - Console")

            # Отключение кнопки закрытия консоли
            Disable_close_button()
            Check_run_by_startup()
        else: # Запуск без exe (например в visual studio code)
            get_saves_settings(True) # Загрузка настроек
            log("Launched without minimizing to tray and other and other gui functions")

        # Проверка наличия токена в памяти
        Init_yaToken(False)

        # Запуск Presence
        Presence.start()

    except KeyboardInterrupt:
        log("Keyboard interrupt received, stopping...")
        Presence.stop()
