import asyncio
import psutil
import pypresence
import time
from enum import Enum
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from yandex_music import Client

client_id = '978995592736944188'
name_prev = str()
strong_find = True #Искать со 100% совпадением названия и автора трека. Иначе будет результат близкий который даст яндекс.

class PlaybackStatus(Enum):
    Unknown = 1
    Opened = 2
    Paused = 3
    Playing = 4
    Stopped = 5

#получаем из winsdk информацию о мультимедиа
async def get_media_info():
    sessions = await MediaManager.request_async()
    current_session = sessions.get_current_session()
    # if current_session and current_session.source_app_user_model_id == "Chrome": #(if read only chrome media)
    if current_session:
        info = await current_session.try_get_media_properties_async()
        info_dict = {song_attr: info.__getattribute__(song_attr) for song_attr in dir(info) if song_attr[0] != '_'}
        info_dict['genres'] = list(info_dict['genres'])
        playback_status = PlaybackStatus(current_session.get_playback_info().playback_status)
        info_dict['playback_status'] = playback_status.name
        return info_dict

    raise Exception('Not have media now')


class Presence:
    def __init__(self) -> None:
        self.token = "" #not needed
        self.client = None
        self.currentTrack = None
        self.rpc = None
        self.running = False
        self.paused = False

    def start(self) -> None:
        if "Discord.exe" not in (p.name() for p in psutil.process_iter()):
            print("[WinYandexMusicRPC] -> Discord is not launched")
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
                return

            ongoing_track = self.getTrack()

            if self.currentTrack != ongoing_track:
                print(f"[WinYandexMusicRPC] -> Changed track to {ongoing_track['label']}")

                if ongoing_track['success']:
                    trackTime = currentTime
                    remainingTime = ongoing_track['durationSec']-2 - (currentTime - trackTime)
                    self.rpc.update(
                        details=ongoing_track['label'],
                        end=currentTime + remainingTime,
                        large_image=ongoing_track['og-image'],
                        large_text='Яндекс Музыка',
                        buttons=[{'label': 'Слушать', 'url': ongoing_track['link']}]
                    )
                else:
                    self.rpc.clear()

                self.currentTrack = ongoing_track

            else:
                if ongoing_track['success'] and ongoing_track["playback"] != PlaybackStatus.Playing.name and not self.paused:
                    self.paused = True
                    print(f"[WinYandexMusicRPC] -> Track {ongoing_track['label']} paused.")

                    if ongoing_track['success']:
                        trackTime = currentTime
                        remainingTime = ongoing_track['durationSec']-2 - (currentTime - trackTime)
                        self.rpc.update(
                            details=ongoing_track['label'],
                            state="На паузе",
                            large_image=ongoing_track['og-image'],
                            large_text='Яндекс Музыка',
                            buttons=[{'label': 'Слушать', 'url': ongoing_track['link']}]
                        )

                elif ongoing_track['success'] and ongoing_track["playback"] == PlaybackStatus.Playing.name and self.paused:
                    print(f"[WinYandexMusicRPC] -> Track {ongoing_track['label']} unpaused.")
                    self.paused = False
            time.sleep(3)


    def getTrack(self) -> dict:
        try:
            current_media_info = asyncio.run(get_media_info())
            name_current = current_media_info["artist"] + " - " + current_media_info["title"]
            global name_prev
            global strong_find
            if str(name_current) != name_prev:
                print("[WinYandexMusicRPC] -> Now listen: "+ name_current)

            name_prev = str(name_current)
            search = self.client.search(name_current)

            if not search.best:
                print(f"[WinYandexMusicRPC] -> cant find music: {name_current}")
                return {
                    'success': False,
                    'label': "No track / Uploaded track",
                    'duration': "Duration: None",
                    'link': "",
                    'og-image': "og-image"
                }
            if  search.best.type not in ['music', 'track', 'podcast_episode']:
                print(f"[WinYandexMusicRPC] -> cant find track: {name_current}, best result is not music")
                return {
                    'success': False,
                    'label': "No track / Uploaded track",
                    'duration': "Duration: None",
                    'link': "",
                    'og-image': "og-image"
                }

            findTrackName = ', '.join([str(elem) for elem in search.best.result.artists_name() ]) + " - " + search.best.result.title
            findTrackName2 = ', '.join([str(elem) for elem in search.best.result.artists_name()[::-1]]) + " - " + search.best.result.title #Меняем местами авторов на всякий случай
            
            if strong_find and findTrackName != name_current and findTrackName2 != name_current:
                print(f"[WinYandexMusicRPC] -> cant find music (strong_find). Now play: {name_current}. But we find: {findTrackName}")
                return {
                    'success': False,
                    'label': "No track / Uploaded track",
                    'duration': "Duration: None",
                    'link': "",
                    'og-image': "og-image"
                }

            track = search.best.result
            trackId = track.trackId.split(":")

            if track:
                return {
                    'success': True,
                    'label': f"{', '.join(track.artists_name())} - {track.title}",
                    'duration': "Duration: None",
                    'link': f"https://music.yandex.ru/album/{trackId[1]}/track/{trackId[0]}/",
                    'durationSec': track.duration_ms// 1000,
                    'playback': current_media_info['playback_status'],
                    'og-image': "https://" + track.og_image[:-2] + "400x400"
                }

        except Exception as exception:
            print(f"[WinYandexMusicRPC] -> Something happened: {exception}")
            return {
                'success': False,
                'label': "No track / Uploaded track",
                'duration': "Duration: None",
                'link': "",
                'og-image': "og-image"
            }

        
if __name__ == '__main__':
    presence = Presence()
    presence.start()