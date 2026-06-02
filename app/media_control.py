import asyncio
from dataclasses import dataclass

from logger import log_error


try:
    from winsdk.windows.media.control import (  # type: ignore
        GlobalSystemMediaTransportControlsSessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus,
    )
    from winsdk.windows.storage.streams import DataReader  # type: ignore

    WINSKD_AVAILABLE = True
except Exception:
    GlobalSystemMediaTransportControlsSessionManager = None  # type: ignore
    GlobalSystemMediaTransportControlsSessionPlaybackStatus = None  # type: ignore
    DataReader = None  # type: ignore
    WINSKD_AVAILABLE = False


@dataclass
class MediaSnapshot:
    available: bool = False
    has_media: bool = False
    is_playing: bool = False
    can_play: bool = False
    can_pause: bool = False
    can_previous: bool = False
    can_next: bool = False
    title: str = ""
    artist: str = ""
    album: str = ""
    app_name: str = ""
    thumbnail: bytes | None = None


class MediaController:
    def __init__(self) -> None:
        self.available = WINSKD_AVAILABLE
        self._last_media_key: tuple[str, str, str, str] | None = None
        self._last_thumbnail: bytes | None = None

    def get_snapshot(self) -> MediaSnapshot:
        if not self.available:
            return MediaSnapshot(available=False)
        try:
            return asyncio.run(self._get_snapshot_async())
        except Exception as exc:
            log_error("Media snapshot failed", exc)
            return MediaSnapshot(available=False)

    def play_pause(self) -> None:
        self._run_control("play_pause")

    def previous(self) -> None:
        self._run_control("try_skip_previous_async")

    def next(self) -> None:
        self._run_control("try_skip_next_async")

    def _run_control(self, method_name: str) -> None:
        if not self.available:
            return
        try:
            asyncio.run(self._run_control_async(method_name))
        except Exception as exc:
            log_error("Media control failed", exc)

    async def _get_manager(self):
        return await GlobalSystemMediaTransportControlsSessionManager.request_async()

    async def _current_session(self):
        manager = await self._get_manager()
        if manager is None:
            return None
        sessions = list(manager.get_sessions() or [])
        current = manager.get_current_session()
        if not sessions:
            return current

        best_session = current or sessions[0]
        best_score = -1
        for session in sessions:
            try:
                playback = session.get_playback_info()
                status = playback.playback_status
                props = await session.try_get_media_properties_async()
                title = str(getattr(props, "title", "") or "")
                artist = str(getattr(props, "artist", "") or "")
                app_id = str(getattr(session, "source_app_user_model_id", "") or "").lower()
                score = 0
                if status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                    score += 100
                if title:
                    score += 25
                if artist:
                    score += 10
                if session == current:
                    score += 5
                if any(token in app_id for token in ("cloudmusic", "netease", "qqmusic", "kugou", "kuwo", "spotify", "music", "media")):
                    score += 8
                if score > best_score:
                    best_score = score
                    best_session = session
            except Exception:
                continue
        return best_session

    async def _get_snapshot_async(self) -> MediaSnapshot:
        session = await self._current_session()
        if session is None:
            return MediaSnapshot(available=True)
        playback_info = session.get_playback_info()
        status = playback_info.playback_status
        controls = getattr(playback_info, "controls", None)
        is_playing = status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
        props = await session.try_get_media_properties_async()
        title = str(getattr(props, "title", "") or "")
        artist = str(getattr(props, "artist", "") or "")
        album = str(getattr(props, "album_title", "") or "")
        app_name = str(getattr(session, "source_app_user_model_id", "") or "")
        media_key = (title, artist, album, app_name)
        if media_key == self._last_media_key:
            thumbnail = self._last_thumbnail
        else:
            thumbnail = await self._read_thumbnail(getattr(props, "thumbnail", None))
            self._last_media_key = media_key
            self._last_thumbnail = thumbnail
        return MediaSnapshot(
            available=True,
            has_media=bool(title or artist or album or app_name),
            is_playing=is_playing,
            can_play=bool(getattr(controls, "is_play_enabled", False)),
            can_pause=bool(getattr(controls, "is_pause_enabled", False)),
            can_previous=bool(getattr(controls, "is_previous_enabled", False)),
            can_next=bool(getattr(controls, "is_next_enabled", False)),
            title=title,
            artist=artist,
            album=album,
            app_name=app_name,
            thumbnail=thumbnail,
        )

    async def _read_thumbnail(self, thumbnail_ref) -> bytes | None:
        if thumbnail_ref is None or DataReader is None:
            return None
        try:
            stream = await thumbnail_ref.open_read_async()
            size = int(stream.size)
            if size <= 0 or size > 4_000_000:
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            data = bytearray(size)
            reader.read_bytes(data)
            return bytes(data)
        except Exception:
            return None

    async def _run_control_async(self, method_name: str) -> None:
        session = await self._current_session()
        if session is None:
            return
        playback_info = session.get_playback_info()
        controls = getattr(playback_info, "controls", None)
        status = playback_info.playback_status
        if method_name == "play_pause":
            if status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                if not bool(getattr(controls, "is_pause_enabled", False)):
                    return
                method = getattr(session, "try_pause_async", None)
            else:
                if not bool(getattr(controls, "is_play_enabled", False)):
                    return
                method = getattr(session, "try_play_async", None)
        elif method_name == "try_skip_previous_async":
            if not bool(getattr(controls, "is_previous_enabled", False)):
                return
            method = getattr(session, method_name, None)
        elif method_name == "try_skip_next_async":
            if not bool(getattr(controls, "is_next_enabled", False)):
                return
            method = getattr(session, method_name, None)
        else:
            method = getattr(session, method_name, None)
        if method is not None:
            await method()
