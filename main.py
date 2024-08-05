from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from config_manager import ConfigManager
from itertools import permutations
from packaging import version
from datetime import timedelta
from yandex_music import Client, exceptions
from colorama import init, Fore, Style

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
import json
import time
import re
import sys
import os
from enum import Enum
from PIL import Image
# Идентификатор клиента Discord для Rich Presence
CLIENT_ID_EN = '1269807014393942046' #Yandex Music
CLIENT_ID_RU = '1217562797999784007' #Яндекс Музыка
CLIENT_ID_RU_DECLINED = '1269826362399522849' #Яндекс Музыку (склонение для активности "Слушает")

# Версия (tag) скрипта для проверки на актуальность через Github Releases
CURRENT_VERSION = "v2.2.1"

# Ссылка на репозиторий
REPO_URL = "https://github.com/FozerG/WinYandexMusicRPC"

# (Опционально) Личный токен Яндекс.Музыки с подпиской Плюс (https://github.com/MarshalX/yandex-music-api/discussions/513)
# - Используется для поиска треков которые не показываются без авторизации 
# - Используется при использовании скрипта из стран где бесплатная Яндекс.Музыка не работает
ya_token = str()

# Флаг для поиска трека с 100% совпадением названия и автора. Иначе будет найден близкий результат.
strong_find = True

# --------- Переменные ниже являются временными и не требуют изменения.
# Переменная для хранения предыдущего трека и избежания дублирования обновлений.
name_prev = str()

# Переменая для хранения полного пути к иконке
icoPath = str()

# Очередь для передачи результатов между процессами
result_queue = multiprocessing.Queue()

#Менеджер настроек
config_manager = ConfigManager()

# Enum для конфигурации кнопок
class ButtonConfig(Enum):
    YANDEX_MUSIC = 1
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

# Функция для получения стартовой позиции начала трека
def get_timeline_position():
    async def async_get_timeline_position():
        sessions = await MediaManager.request_async()
        current_session = sessions.get_current_session()
        if current_session:
            position = current_session.get_timeline_properties().position
            return position
        else:
            return timedelta(seconds=0)
    
    return asyncio.run(async_get_timeline_position())

# Функция для получения информации о мультимедийном контенте через Windows SDK
def get_media_info():
    async def async_get_media_info():
        sessions = await MediaManager.request_async()
        current_session = sessions.get_current_session()
        if current_session:
            info = await current_session.try_get_media_properties_async()
            info_dict = {song_attr: getattr(info, song_attr) for song_attr in dir(info) if not song_attr.startswith('_')}
            info_dict['genres'] = list(info_dict['genres'])
            playback_status = PlaybackStatus(current_session.get_playback_info().playback_status)
            info_dict['playback_status'] = playback_status.name
            return info_dict
        raise Exception('The music is not playing right now.')
    
    return asyncio.run(async_get_media_info())

class Presence:
    client = None
    currentTrack = None
    rpc = None
    running = False
    paused = False
    paused_time = 0 
    exe_names = ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"]

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
                        remainingTime = ongoing_track['durationSec'] - int(ongoing_track['start-time'].total_seconds())
                        presence_args = {
                            'activity_type': activityType_config.value,
                            'details': ongoing_track['title'],
                            'state': ongoing_track['artist'],
                            'end': currentTime + remainingTime,
                            'large_image': ongoing_track['og-image'],
                            'large_text': ongoing_track['album']
                        }

                        if button_config != ButtonConfig.NEITHER:
                            presence_args['buttons'] = build_buttons(ongoing_track['link'])
                        
                        if activityType_config == ActivityTypeConfig.LISTENING:
                            presence_args['large_text'] = f"{'Track length' if language_config == LanguageConfig.ENGLISH else 'Длительность'} - {ongoing_track['formatted_duration']}"
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
        try:
            current_media_info = get_media_info()
            if not current_media_info:
                log("No media information returned from get_media_info", LogType.Error)
                return {'success': False}
            
            artist = current_media_info.get("artist", "").strip()
            title = current_media_info.get("title", "").strip()

            if not artist or not title:
                log("Winsdk returned empty string for artist or title", LogType.Error)
                return {'success': False}
            name_current = artist + " - " + title
            global name_prev
            global strong_find
            if str(name_current) != name_prev:
                log("Now listening to " + name_current)
            else: #Если песня уже играет, то не нужно ее искать повторно. Просто вернем её с актуальным статусом паузы и позиции.
                currentTrack_copy = Presence.currentTrack.copy()
                position = get_timeline_position()
                currentTrack_copy["start-time"] = position
                currentTrack_copy["playback"] = current_media_info['playback_status']
                return currentTrack_copy

            name_prev = str(name_current)
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
                all_variants = list(permutations(artists))
                all_variants = [list(variant) for variant in all_variants]
                findTrackNames = []
                for variant in all_variants:
                    findTrackNames.append(', '.join([str(elem) for elem in variant]) + " - " + trackFromSearch.title)
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
            startTime = get_timeline_position()
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
                    'start-time': startTime,
                    'playback': current_media_info['playback_status'],
                    'og-image': "https://" + track.og_image[:-2] + "400x400"
                }
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
    if button_config == ButtonConfig.YANDEX_MUSIC:
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
    input("Press Enter to close the program.")
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
def toggle_strong_find(icon, item):
    global strong_find
    strong_find = not strong_find
    log(f'Bool strong_find set state: {strong_find}')

def toggle_console():
    if win32gui.IsWindowVisible(window):
        win32gui.ShowWindow(window, win32con.SW_HIDE)
    else:
        win32gui.ShowWindow(window, win32con.SW_SHOW)

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
def get_saves_settings():
    global activityType_config
    global button_config
    global language_config
    activityType_config = config_manager.get_enum_setting('UserSettings', 'activity_type', ActivityTypeConfig, fallback=ActivityTypeConfig.LISTENING)
    button_config = config_manager.get_enum_setting('UserSettings', 'buttons_settings', ButtonConfig, fallback=ButtonConfig.BOTH)
    language_config = config_manager.get_enum_setting('UserSettings', 'language', LanguageConfig, fallback=LanguageConfig.RUSSIAN)
    
    log(f"Loaded settings: {Style.RESET_ALL}activityType_config = {activityType_config}, button_config = {button_config}, language_config = {language_config}", LogType.Update_Status)
    

# Функция для обновления имени аккаунта в меню
def update_account_name(icon, new_account_name):
    settingsMenu = pystray.Menu(
        pystray.MenuItem(f"Logged in as - {new_account_name}", lambda: None, enabled=False),
        pystray.MenuItem('Login to account...', lambda: Init_yaToken(True)),
        pystray.MenuItem('Toggle strong_find', toggle_strong_find, checked=lambda item: strong_find),
    )
    
    icon.menu = pystray.Menu(
        pystray.MenuItem("Hide/Show Console", toggle_console, default=True),
        pystray.MenuItem("Settings", settingsMenu),
        pystray.MenuItem("GitHub", tray_click),
        pystray.MenuItem("Exit", tray_click)
    )

# Функция для создания иконки с меню
def create_tray_icon():
    tray_image = Image.open(Get_IconPath())
    account_name = get_account_name()
    
    settingsMenu = pystray.Menu(
        pystray.MenuItem(f"Logged in as - {account_name}", lambda: None, enabled=False),
        pystray.MenuItem('Login to account...', lambda: Init_yaToken(True)),
        pystray.MenuItem('Toggle strong_find', toggle_strong_find, checked=lambda item: strong_find),
    )
    
    icon = pystray.Icon("WinYandexMusicRPC", tray_image, "WinYandexMusicRPC", menu=pystray.Menu(
        pystray.MenuItem("Hide/Show Console", toggle_console, default=True),
        pystray.MenuItem("Settings", settingsMenu),
        pystray.MenuItem("GitHub", tray_click),
        pystray.MenuItem("Exit", tray_click)
    ))
    return icon

# Функция для запуска иконки в отдельном потоке
def tray_thread(icon):
    icon.run()

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
    result = getToken.update_token(icon_path)
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
                update_account_name(mainMenu, get_account_name())
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

        return f"{resources_path}/assets/tray.png"
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
            # Запуск потока для трея
            mainMenu = create_tray_icon() 
            icon_thread = threading.Thread(target=tray_thread, args=(mainMenu,))
            icon_thread.daemon = True
            icon_thread.start()

            # Получение окна консоли
            window = win32console.GetConsoleWindow()
            
            if Is_already_running():
                log("WinYandexMusicRPC is already running.", LogType.Error)
                WaitAndExit()
            
            # Установка заголовка окна консоли
            win32console.SetConsoleTitle("WinYandexMusicRPC - Console")
            
            # Отключение кнопки закрытия консоли
            Disable_close_button()
            win32gui.ShowWindow(window, win32con.SW_SHOW)  # Показываем окно т.к оно свернуто с помощью "/min"
            if window:
                log("Minimize to system tray in 3 seconds...")
                time.sleep(3)
                win32gui.ShowWindow(window, win32con.SW_HIDE)  # Скрытие окна консоли
            else:
                log("Console window not found", LogType.Error)
        else: # Запуск без exe (например в visual studio code)
            log("Launched without minimizing to tray and other and other gui functions")

        # Проверка наличия токена в памяти
        Init_yaToken(False)
        # Загрузка настроек
        get_saves_settings()
        # Запуск Presence   
        Presence.start()
        
    except KeyboardInterrupt:
        log("Keyboard interrupt received, stopping...")
        Presence.stop()
