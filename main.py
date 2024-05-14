import asyncio
from datetime import timedelta
import psutil
import pypresence
import time
from enum import Enum
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from yandex_music import Client
from itertools import permutations
import psutil
import requests
import os
import sys
import signal
import webbrowser

# Трей
import pystray
from PIL import Image
import threading
import win32gui, win32con

# Идентификатор клиента Discord для Rich Presence
client_id = '978995592736944188'

# Версия (tag) скрипта для проверки на актуальность через Github Releases
current_version = "v1.8.2"

# Флаг для поиска трека с 100% совпадением названия и автора. Иначе будет найден близкий результат.
strong_find = True

# Переменная для хранения предыдущего трека и избежания дублирования обновлений.
name_prev = str()

# Иконка для трея
resources_path = sys._MEIPASS
tray_image = Image.open(f"{resources_path}/assets/tray.png")

# Ссылка на репо
repo_url = "https://github.com/FozerG/WinYandexMusicRPC"

# Enum для статуса воспроизведения мультимедийного контента.
class PlaybackStatus(Enum):
    Unknown = 0
    Closed = 1
    Opened = 2
    Paused = 3
    Playing = 4
    Stopped = 5
    
def log(text):
    print("[WinYandexMusicRPC] -> {}".format(text))

log("Minimizing to tray in 1 second.")

# Необходимо захватить окно как можно скорее, иначе может закрыться другое
window = win32gui.GetForegroundWindow()

time.sleep(1)

win32gui.ShowWindow(window, win32con.SW_HIDE)

# Действия для кнопок
def tray_click(icon, query):
    match str(query):
        case "GitHub":
            webbrowser.open(repo_url,  new=2)

        case "Show Console":
            win32gui.ShowWindow(window, win32con.SW_SHOW)

        case "Hide Console":
            win32gui.ShowWindow(window, win32con.SW_HIDE)

        case "Exit":
            icon.stop()
            os.kill(os.getpid(), signal.SIGILL)

def tray_thread():
    tray_icon = pystray.Icon("WinYandexMusicRPC", tray_image, "WinYandexMusicRPC", menu=pystray.Menu(
        pystray.MenuItem("GitHub", tray_click),
        pystray.MenuItem("Show Console", tray_click),
        pystray.MenuItem("Hide Console", tray_click),
        pystray.MenuItem("Exit", tray_click)))

    tray_icon.run()

tray_thread = threading.Thread(target=tray_thread)
tray_thread.start()

# Асинхронная функция для получения информации о стартовой позиции начала трека
async def get_timeline_position():
    sessions = await MediaManager.request_async()
    current_session = sessions.get_current_session()
    if current_session:
        position = current_session.get_timeline_properties().position
        return position
    else:
        return timedelta(seconds=0)
        
# Асинхронная функция для получения информации о мультимедийном контенте через Windows SDK.
async def get_media_info():
    sessions = await MediaManager.request_async()
    current_session = sessions.get_current_session()
    if current_session:
        info = await current_session.try_get_media_properties_async()
        info_dict = {song_attr: info.__getattribute__(song_attr) for song_attr in dir(info) if song_attr[0] != '_'}
        info_dict['genres'] = list(info_dict['genres'])
        playback_status = PlaybackStatus(current_session.get_playback_info().playback_status)
        info_dict['playback_status'] = playback_status.name
        return info_dict
    raise Exception('The music is not playing right now.')

# Класс для работы с Rich Presence в Discord.
class Presence:
    try:
        def __init__(self) -> None:
            self.client = None
            self.currentTrack = None
            self.rpc = None
            self.running = False
            self.paused = False
            self.paused_time = 0 


        # Метод для запуска Rich Presence.
        def start(self) -> None:
            exe_names = ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"]
            if not any(name in (p.name() for p in psutil.process_iter()) for name in exe_names):
                log("Discord is not launched")
                WaitAndExit()
                return

            log("Launched. Check the actual version...")
            GetLastVersion(repo_url)
            self.rpc = pypresence.Presence(client_id)
            self.rpc.connect()
            self.client = Client().init()
            self.running = True
            self.currentTrack = None

            while self.running:
                currentTime = time.time()

                if not any(name in (p.name() for p in psutil.process_iter()) for name in exe_names):
                    log("Discord was closed")
                    WaitAndExit()
                    return

                ongoing_track = self.getTrack()
                if self.currentTrack != ongoing_track : # проверяем что песня не играла до этого, т.к она просто может быть снята с паузы.
                    if ongoing_track['success']: 
                        if self.currentTrack is not None and 'label' in self.currentTrack and self.currentTrack['label'] is not None:
                            if ongoing_track['label'] != self.currentTrack['label']: 
                                log(f"Changed track to {ongoing_track['label']}")
                        else:
                            log(f"Changed track to {ongoing_track['label']}")
                        self.paused_time = 0
                        trackTime = currentTime
                        remainingTime = ongoing_track['durationSec'] - int(ongoing_track['start-time'].total_seconds())
                        self.rpc.update(
                            details=ongoing_track['title'],
                            state=ongoing_track['artist'],
                            end=currentTime + remainingTime,
                            large_image=ongoing_track['og-image'],
                            large_text=ongoing_track['album'],

                            buttons=[{'label': 'Listen on Yandex.Music', 'url': ongoing_track['link']}] #Для текста кнопки есть ограничение в 32 байта. Кириллица считается за 2 байта.
                                                                                                #Если превысить лимит то Discord RPC не будет виден другим пользователям.
                        )
                    else:
                        self.rpc.clear()
                        log(f"Clear RPC")

                    self.currentTrack = ongoing_track

                else: #Песня не новая, проверяем статус паузы
                    if ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and not self.paused:
                        self.paused = True
                        log(f"Track {ongoing_track['label']} on pause")

                        if ongoing_track['success']:
                            self.rpc.update(
                                details=ongoing_track['title'],
                                state=ongoing_track['artist'],
                                large_image=ongoing_track['og-image'],
                                large_text=ongoing_track['album'],
                                buttons=[{'label': 'Listen on Yandex.Music', 'url': ongoing_track['link']}], #Для текста кнопки есть ограничение в 32 байта. Кириллица считается за 2 байта.
                                                                                                        #Если превысить лимит то Discord RPC не будет виден другим пользователям.
                                small_image="https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/pause.png",
                                small_text="На паузе"
                            )

                    elif ongoing_track['success'] and ongoing_track["playback"] == PlaybackStatus.Playing.name and self.paused:
                        log(f"Track {ongoing_track['label']} off pause.")
                        self.paused = False

                    elif ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and self.paused and trackTime != 0:
                        self.paused_time = currentTime - trackTime
                        if self.paused_time > 5 * 60:  # если пауза больше 5 минут
                            trackTime = 0
                            self.rpc.clear()
                            log(f"Clear RPC due to paused for more than 5 minutes")
                    else:
                        self.paused_time = 0  # если трек продолжает играть, сбрасываем paused_time

                time.sleep(3)

        # Метод для получения информации о текущем треке.
        def getTrack(self) -> dict:
            try:
                current_media_info = asyncio.run(get_media_info())
                name_current = current_media_info["artist"] + " - " + current_media_info["title"]
                global name_prev
                global strong_find
                if str(name_current) == " - ":
                    log("Winsdk returned empty string")
                    {'success': False}
                if str(name_current) != name_prev:
                    log("Now listening to " + name_current)
                else: #Если песня уже играет, то не нужно ее искать повторно. Просто вернем её с актуальным статусом паузы и позиции.
                    currentTrack_copy = self.currentTrack.copy()
                    position = asyncio.run(get_timeline_position())
                    currentTrack_copy["start-time"] = position
                    currentTrack_copy["playback"] = current_media_info['playback_status']
                    return currentTrack_copy

                name_prev = str(name_current)
                search = self.client.search(name_current, True, "all", 0, False)

                if search.tracks == None:
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

                if finalTrack == None:
                    print('\n'.join(debugStr))
                    log(f"Can't find the song (strong_find): {name_current}")
                    return {'success': False}

                track = finalTrack
                trackId = track.trackId.split(":")
                startTime = asyncio.run(get_timeline_position())
                if track:
                    return {
                        'success': True,
                        'title': TrimString(track.title, 40),
                        'artist': TrimString(f"{', '.join(track.artists_name())}",40),
                        'album': TrimString(track.albums[0].title,25),
                        'label': TrimString(f"{', '.join(track.artists_name())} - {track.title}",50),
                        'duration': "Duration: None",
                        'link': f"https://music.yandex.ru/album/{trackId[1]}/track/{trackId[0]}/",
                        'durationSec': track.duration_ms // 1000,
                        'start-time': startTime,
                        'playback': current_media_info['playback_status'],
                        'og-image': "https://" + track.og_image[:-2] + "400x400"
                    }

            except Exception as exception:
                log(f"Something happened: {exception}")
                return {'success': False}

    except Exception as exception:
        win32gui.ShowWindow(window, win32con.SW_SHOW)
        log("Something bad happened in the presence class!")
        log(f"More info: {exception}")
        WaitAndExit()

def WaitAndExit():
    input("Press Enter to close the program.")

def TrimString(string, maxChars):
    if len(string) > maxChars:
        return string[:maxChars] + "..."
    else:
        return string
    
def GetLastVersion(repoUrl):
    try:
        global current_version
        response = requests.get(repoUrl + '/releases/latest')
        response.raise_for_status()
        latest_version = response.url.split('/')[-1]
        if current_version != latest_version:
            log(f"A new version has been released on GitHub. You are using - {current_version}. A new version - {latest_version}, you can download it at {repoUrl + '/releases/tag/' + latest_version}")
        else:
            log(f"You are using the latest version of the script")
        
    except requests.exceptions.RequestException as e:
        log("Error getting latest version:", e)

if __name__ == '__main__':
    presence = Presence()
    presence.start()