import asyncio
import psutil
import pypresence
import time
from enum import Enum
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from yandex_music import Client
from itertools import permutations
# Идентификатор клиента Discord для Rich Presence
client_id = '978995592736944188'

# Флаг для поиска трека с 100% совпадением названия и автора. Иначе будет найден близкий результат.
strong_find = True

# Переменная для хранения предыдущего трека и избежания дублирования обновлений.
name_prev = str()

# Enum для статуса воспроизведения мультимедийного контента.
class PlaybackStatus(Enum):
    Unknown = 0,1
    Opened = 2
    Paused = 3
    Playing = 4
    Stopped = 5

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
    def __init__(self) -> None:
        self.client = None
        self.currentTrack = None
        self.rpc = None
        self.running = False
        self.paused = False

    # Метод для запуска Rich Presence.
    def start(self) -> None:
        if "Discord.exe" not in (p.name() for p in psutil.process_iter()):
            print("[WinYandexMusicRPC] -> Discord is not launched")
            WaitAndExit()
            return

        self.rpc = pypresence.Presence(client_id)
        self.rpc.connect()
        self.client = Client().init()
        self.running = True
        self.currentTrack = None

        while self.running:
            currentTime = time.time()

            if "Discord.exe" not in (p.name() for p in psutil.process_iter()):
                print("[WinYandexMusicRPC] -> Discord was closed")
                WaitAndExit()
                return

            ongoing_track = self.getTrack()

            if self.currentTrack != ongoing_track :
                if ongoing_track['success']: # проверяем что песня не играла до этого, т.к она просто может быть снята с паузы.
                    if self.currentTrack is not None and 'label' in self.currentTrack and self.currentTrack['label'] is not None:
                        if ongoing_track['label'] != self.currentTrack['label']: 
                            print(f"[WinYandexMusicRPC] -> Changed track to {ongoing_track['label']}")
                    else:
                        print(f"[WinYandexMusicRPC] -> Changed track to {ongoing_track['label']}")

                    trackTime = currentTime
                    remainingTime = ongoing_track['durationSec'] - 2 - (currentTime - trackTime)
                    self.rpc.update(
                        details=ongoing_track['label'],
                        end=currentTime + remainingTime,
                        large_image=ongoing_track['og-image'],
                        large_text='Яндекс Музыка',
                        buttons=[{'label': 'Слушать', 'url': ongoing_track['link']}]
                    )
                else:
                    self.rpc.clear()
                    print(f"[WinYandexMusicRPC] -> Clear RPC")

                self.currentTrack = ongoing_track

            else:
                if ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and not self.paused:
                    self.paused = True
                    print(f"[WinYandexMusicRPC] -> Track {ongoing_track['label']} on pause")

                    if ongoing_track['success']:
                        trackTime = currentTime
                        remainingTime = ongoing_track['durationSec'] - 2 - (currentTime - trackTime)
                        self.rpc.update(
                            details=ongoing_track['label'],
                            state="На паузе",
                            large_image=ongoing_track['og-image'],
                            large_text='Яндекс Музыка',
                            buttons=[{'label': 'Слушать', 'url': ongoing_track['link']}]
                        )

                elif ongoing_track['success'] and ongoing_track["playback"] == PlaybackStatus.Playing.name and self.paused:
                    print(f"[WinYandexMusicRPC] -> Track {ongoing_track['label']} off pause.")
                    self.paused = False
            time.sleep(3)

    # Метод для получения информации о текущем треке.
    def getTrack(self) -> dict:
        try:
            current_media_info = asyncio.run(get_media_info())
            name_current = current_media_info["artist"] + " - " + current_media_info["title"]
            global name_prev
            global strong_find
            if str(name_current) != name_prev:
                print("[WinYandexMusicRPC] -> Now listen: " + name_current)
            else: #Если песня уже играет, то не нужно ее искать повторно. Просто вернем её с актуальным статусом паузы.
                currentTrack_copy = self.currentTrack.copy()
                currentTrack_copy["playback"] = current_media_info['playback_status']
                return currentTrack_copy

            name_prev = str(name_current)
            search = self.client.search(name_current, True, "all", 0, False)

            if not search.best:
                print(f"[WinYandexMusicRPC] -> Can't find the song: {name_current}")
                return {'success': False}
            if search.best.type not in ['music', 'track', 'podcast_episode']:
                print(f"[WinYandexMusicRPC] -> Can't find the song: {name_current}, the best result has the wrong type")
                return {'success': False}
            findTrackName = ', '.join([str(elem) for elem in search.best.result.artists_name()]) + " - " + \
                             search.best.result.title

            # Авторы могут отличатся положением, поэтому делаем все возможные варианты их порядка.
            artists = search.best.result.artists_name()
            all_variants = list(permutations(artists))
            all_variants = [list(variant) for variant in all_variants]
            findTrackNames = []
            for variant in all_variants:
                findTrackNames.append(', '.join([str(elem) for elem in variant]) + " - " + search.best.result.title)
            # Также может отличаться регистр, так что приведём всё в один регистр.    
            boolNameCorrect = any(name_current.lower() == element.lower() for element in findTrackNames)

            if strong_find and not boolNameCorrect:
                print(f"[WinYandexMusicRPC] -> Cant find the song (strong_find). Now play: {name_current}. But we find: {findTrackName}")
                return {'success': False}
                    

            track = search.best.result
            trackId = track.trackId.split(":")

            if track:
                return {
                    'success': True,
                    'label': f"{', '.join(track.artists_name())} - {track.title}",
                    'duration': "Duration: None",
                    'link': f"https://music.yandex.ru/album/{trackId[1]}/track/{trackId[0]}/",
                    'durationSec': track.duration_ms // 1000,
                    'playback': current_media_info['playback_status'],
                    'og-image': "https://" + track.og_image[:-2] + "400x400"
                }

        except Exception as exception:
            print(f"[WinYandexMusicRPC] -> Something happened: {exception}")
            return {'success': False}

def WaitAndExit():
    time.sleep(3)
    exit

if __name__ == '__main__':
    presence = Presence()
    presence.start()
