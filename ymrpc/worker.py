import asyncio
import logging
import time
from queue import Empty, Queue
from threading import Event

from PyQt6.QtCore import QThread, pyqtSignal
from yandex_music import Client

from .config import ConfigStore
from .discord import DiscordConnection
from .i18n import message
from .media import WindowsMediaSource
from .models import CaptureMode, Track
from .presence import PlaybackState, PresenceGrace, build_payload, client_id
from .search import UNUSED_SOURCES, TrackResolver
from .tokens import TokenStore
from .version_check import latest_release
from .ynison import YnisonSource, correct_pause

logger = logging.getLogger(__name__)


class PresenceWorker(QThread):
    sessions_changed = pyqtSignal(tuple)
    status_changed = pyqtSignal(object)
    account_changed = pyqtSignal(object)
    authentication_finished = pyqtSignal(bool, object)
    update_checked = pyqtSignal(object)
    track_changed = pyqtSignal(object)

    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._ynison_token = None
        self._stop = Event()
        self._wake = Event()
        self._commands: Queue[tuple[str, str | None]] = Queue()

    def refresh(self) -> None:
        self._wake.set()

    def authenticate(self, token: str) -> None:
        self._commands.put(("login", token))
        self.refresh()

    def logout(self) -> None:
        self._commands.put(("logout", None))
        self.refresh()

    def check_updates(self, automatic: bool = False) -> None:
        self._commands.put(("startup_updates" if automatic else "check_updates", None))
        self.refresh()

    def stop(self) -> None:
        self._stop.set()
        self.refresh()

    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        media_loop = asyncio.new_event_loop()
        source = WindowsMediaSource()
        ynison = YnisonSource()
        resolver = TrackResolver()
        discord = DiscordConnection()
        playback = PlaybackState()
        grace = PresenceGrace()
        previous_settings = self.config.settings
        tokens = TokenStore()
        session_ids = None
        last_error = None
        last_media = None
        last_status = None
        confirmed = None
        last_ignored = None
        last_corrected = None
        try:
            self._load_account(tokens, resolver)
            while not self._stop.is_set():
                self._wake.clear()
                self._process_commands(tokens, resolver)
                settings = self.config.settings
                if settings != previous_settings:
                    grace = PresenceGrace()
                    if settings.capture_mode != previous_settings.capture_mode:
                        media_loop.run_until_complete(ynison.close())
                        discord.publish(client_id(settings), None)
                        playback = PlaybackState()
                        confirmed = None
                        last_media = None
                        last_status = None
                        logger.info("Capture mode changed: %s", settings.capture_mode.value)
                    if settings.selected_session != previous_settings.selected_session:
                        confirmed = None
                    previous_settings = settings
                try:
                    if settings.capture_mode == CaptureMode.YNISON:
                        result = media_loop.run_until_complete(ynison.read(self._ynison_token))
                        if settings.fix_ynison_pause:
                            result = media_loop.run_until_complete(correct_pause(result, source))
                        corrected = result.media.identity if result.pause_corrected else None
                        if corrected and corrected != last_corrected:
                            logger.info(
                                "Ynison pause corrected via Windows.Media.Control: %s", corrected
                            )
                        last_corrected = corrected
                        if settings != self.config.settings or self._stop.is_set():
                            continue
                        key = (
                            (result.media.identity, result.media.status)
                            if result.media
                            else result.state
                        )
                        if key != last_media:
                            logger.info(
                                "Ynison capture: state=%s; media=%s", result.state, result.media
                            )
                            last_media = key
                        self._publish_ynison(result, settings, playback, grace, discord)
                        self._wake.wait(0.5)
                        continue
                    media = media_loop.run_until_complete(source.read(settings.selected_session))
                    media_key = (media.identity, media.status) if media else None
                    if media_key != last_media:
                        if media:
                            logger.info(
                                "Media received: app=%r; artist=%r; title=%r; album=%r; "
                                "duration=%.1fs; position=%.1fs; status=%s",
                                media.source,
                                media.artist,
                                media.title,
                                media.album,
                                media.duration,
                                media.position,
                                media.status.name,
                            )
                        else:
                            logger.info("Media session ended")
                        last_media = media_key
                    payload = None
                    track = None
                    search_state = "idle"
                    source_states = UNUSED_SOURCES
                    ignored_info = ""
                    verification_session = settings.selected_session
                    ignored_key = None
                    if media:
                        result = resolver.resolve(media)
                        if result.track:
                            confirmed = (media.identity, result)
                        elif not settings.show_unknown_media:
                            reason = {
                                "searching": message("verification.searching"),
                                "unavailable": message("verification.unavailable"),
                            }.get(result.state, message("verification.not_found"))
                            ignored_info = message(
                                "verification.skipped", source=media.source, reason=reason
                            )
                            ignored_key = (media.identity, result.state)
                            if ignored_key != last_ignored:
                                logger.info(
                                    "Media %s: app=%r; artist=%r; title=%r; reason=%s",
                                    "pending verification"
                                    if result.state == "searching"
                                    else "ignored",
                                    media.source,
                                    media.artist,
                                    media.title,
                                    result.state,
                                )
                            if confirmed and settings.selected_session == "Automatic":
                                identity, previous_result = confirmed
                                fallback = media_loop.run_until_complete(source.read(identity[0]))
                                if fallback is not None and fallback.identity == identity:
                                    media = fallback
                                    result = previous_result
                                    verification_session = fallback.source
                        track = result.track
                        search_state = result.state
                        source_states = result.sources
                    last_ignored = ignored_key
                    visible = playback.visible(media, settings.pause_timeout, time.monotonic())
                    status = message("status.waiting")
                    if media is not None and visible:
                        # Search may outlive a track when the user skips several songs.
                        current = media_loop.run_until_complete(source.read(verification_session))
                        if current is None or current.identity != media.identity:
                            if not grace.hold(False, True, time.monotonic()):
                                discord.publish(client_id(settings), None)
                            self._wake.wait(0.2)
                            continue
                        media = current
                        if playback.visible(media, settings.pause_timeout, time.monotonic()):
                            if track or (
                                settings.show_unknown_media and search_state != "searching"
                            ):
                                displayed = track or Track(
                                    media.title,
                                    media.artist,
                                    media.album,
                                    media.duration,
                                )
                                payload = build_payload(media, displayed, settings, time.time())
                                status = (
                                    message("status.active")
                                    if track
                                    else message("status.unverified")
                                )
                            else:
                                status = {
                                    "searching": message("status.searching"),
                                    "unavailable": message("status.unavailable"),
                                }.get(search_state, message("status.not_found"))
                    elif media is not None:
                        status = message("status.paused")
                    if self._stop.is_set():
                        break
                    if settings != self.config.settings:
                        continue
                    if grace.hold(
                        payload is not None,
                        media is None or (visible and search_state == "searching"),
                        time.monotonic(),
                    ):
                        self._wake.wait(0.2)
                        continue
                    delivered = discord.publish(client_id(settings), payload)
                    if delivered is False and payload is not None:
                        status = message("status.discord_unavailable")
                    if status != last_status:
                        logger.info(
                            "Presence: requested=%s; delivered=%s; search=%s; source=%s",
                            payload is not None,
                            delivered,
                            search_state,
                            track.source if track else "none",
                        )
                        last_status = status
                    self.status_changed.emit(status)
                    self.track_changed.emit(
                        (media, track, search_state, source_states, ignored_info)
                    )
                    last_error = None
                except Exception as error:
                    error_type = type(error).__name__
                    if error_type != last_error:
                        logger.warning(
                            "Media polling failed (%s): %s; waiting for recovery", error_type, error
                        )
                        last_error = error_type
                    if grace.hold(False, True, time.monotonic()):
                        self._wake.wait(0.2)
                        continue
                    playback.visible(None, settings.pause_timeout, time.monotonic())
                    discord.publish(client_id(settings), None)
                    self.status_changed.emit(message("status.media_unavailable"))
                    self.track_changed.emit((None, None, "unavailable"))
                finally:
                    if source.session_ids != session_ids:
                        session_ids = source.session_ids
                        self.sessions_changed.emit(session_ids)
                self._wake.wait(1)
        finally:
            media_loop.run_until_complete(source.close())
            media_loop.run_until_complete(ynison.close())
            discord.close()
            resolver.close()
            media_loop.run_until_complete(media_loop.shutdown_asyncgens())
            media_loop.close()
            pythoncom.CoUninitialize()
            logger.info("Presence worker stopped")

    def _publish_ynison(self, result, settings, playback, grace, discord):
        media, track = result.media, result.track
        visible = playback.visible(media, settings.pause_timeout, time.monotonic())
        payload = build_payload(media, track, settings, time.time()) if visible and track else None
        if grace.hold(
            payload is not None, result.state in ("connecting", "unavailable"), time.monotonic()
        ):
            return
        delivered = discord.publish(client_id(settings), payload)
        status = {
            "auth_required": message("status.ynison_auth"),
            "connecting": message("status.ynison_connecting"),
            "unavailable": message("status.ynison_unavailable"),
            "unsupported": message("status.ynison_unsupported"),
            "idle": message("status.ynison_idle"),
        }.get(result.state, message("status.active") if visible else message("status.paused"))
        if delivered is False and payload is not None:
            status = message("status.discord_unavailable")
        self.status_changed.emit(status)
        self.track_changed.emit(
            (
                media,
                track,
                result.state,
                UNUSED_SOURCES,
                "",
                {
                    "device": result.device_name,
                    "pause_corrected": result.pause_corrected,
                    "auth_required": result.state == "auth_required",
                },
            )
        )

    def _load_account(self, tokens: TokenStore, resolver: TrackResolver) -> None:
        try:
            token = tokens.load()
            self._ynison_token = token
            if token:
                client = Client(token=token)
                resolver.set_client(client)
                client.init(timeout=5)
                self.account_changed.emit(
                    client.me.account.display_name or message("account.fallback")
                )
        except Exception as error:
            logger.warning(
                "Account details unavailable (%s); continuing media polling", type(error).__name__
            )
            self.status_changed.emit(message("account.connection_failed"))

    def _process_commands(self, tokens: TokenStore, resolver: TrackResolver) -> None:
        while not self._stop.is_set():
            try:
                action, token = self._commands.get_nowait()
            except Empty:
                return
            try:
                if action == "login" and token:
                    client = tokens.validate_and_save(token)
                    self._ynison_token = token
                    resolver.set_client(client)
                    self.account_changed.emit(
                        client.me.account.display_name or message("account.fallback")
                    )
                    self.authentication_finished.emit(True, message("account.signed_in"))
                elif action == "logout":
                    tokens.delete()
                    self._ynison_token = None
                    resolver.set_client(None)
                    self.account_changed.emit(None)
                    self.authentication_finished.emit(True, message("account.logged_out"))
                elif action in ("check_updates", "startup_updates"):
                    try:
                        url = latest_release()
                        logger.info("Update check: %s", url or "already up to date")
                        notification = (
                            message("updates.available", url=url)
                            if url
                            else message("updates.current")
                        )
                    except (OSError, ValueError, KeyError):
                        logger.warning("Update check unavailable")
                        if action == "startup_updates":
                            continue
                        notification = message("updates.failed")
                    if action == "startup_updates" and not url:
                        continue
                    self.update_checked.emit(notification)
            except Exception as error:
                logger.warning("Account operation failed (%s)", type(error).__name__)
                self.authentication_finished.emit(False, message("account.failed"))
