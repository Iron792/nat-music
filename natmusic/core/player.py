"""PyTgCalls v2 playback engine with EQ filters, seek, volume, and auto-advance."""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from pytgcalls import PyTgCalls, filters
from pytgcalls.types import AudioQuality, MediaStream, VideoQuality
from pytgcalls.types.update import Update

from natmusic.core.queue import QueueManager, Track

logger = logging.getLogger("natmusic.player")

EQ_PRESETS: dict[str, dict[str, str]] = {
    "flat": {
        "label": "Flat (Default)",
        "ffmpeg": "",
    },
    "bass": {
        "label": "Bass Boost",
        "ffmpeg": "-af bass=g=8:f=110:w=0.6",
    },
    "studio": {
        "label": "Studio Clarity",
        "ffmpeg": "-af equalizer=f=1000:width_type=h:width=200:g=3,equalizer=f=8000:width_type=h:width=500:g=4",
    },
    "vocal": {
        "label": "Vocal Boost",
        "ffmpeg": "-af equalizer=f=300:width_type=h:width=200:g=-2,equalizer=f=3000:width_type=h:width=1000:g=5",
    },
    "nightcore": {
        "label": "Nightcore (1.2x)",
        "ffmpeg": "-af asetrate=48000*1.2,aresample=48000,atempo=1.0",
    },
}


def _quality_enum(quality_name: str) -> tuple[AudioQuality, VideoQuality]:
    q = quality_name.lower()
    if q == "studio":
        return AudioQuality.STUDIO, VideoQuality.HD_720p
    if q == "medium":
        return AudioQuality.MEDIUM, VideoQuality.SD_480p
    return AudioQuality.HIGH, VideoQuality.HD_720p


class NatPlayer:
    """High-level VC player coordinating PyTgCalls and QueueManager."""

    def __init__(
        self,
        calls: PyTgCalls,
        queues: QueueManager,
        on_track_started: Callable[[int, Track], Awaitable[None]] | None = None,
        on_queue_ended: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self.calls = calls
        self.queues = queues
        self.on_track_started = on_track_started
        self.on_queue_ended = on_queue_ended
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.calls.on_update(filters.stream_end())
        async def _on_stream_end(_: PyTgCalls, update: Update) -> None:
            chat_id = update.chat_id
            next_track = await self.queues.advance(chat_id)
            if next_track is not None:
                state = self.queues.get_state(chat_id)
                await self.play_stream(
                    chat_id,
                    next_track,
                    eq_preset=state.eq_preset,
                    volume=state.volume,
                )
                if self.on_track_started:
                    await self.on_track_started(chat_id, next_track)
            else:
                await self.leave(chat_id)
                if self.on_queue_ended:
                    await self.on_queue_ended(chat_id)

    def build_media_stream(
        self,
        track: Track,
        quality: str = "high",
        eq_preset: str = "flat",
        seek_sec: int = 0,
    ) -> MediaStream:
        audio_q, video_q = _quality_enum(quality)
        ffmpeg_parts: list[str] = []
        if seek_sec > 0 and not track.is_live:
            ffmpeg_parts.append(f"-ss {seek_sec}")
        eq_flag = EQ_PRESETS.get(eq_preset, {}).get("ffmpeg", "")
        if eq_flag:
            ffmpeg_parts.append(eq_flag)

        ffmpeg_params = " ".join(ffmpeg_parts) if ffmpeg_parts else None
        return MediaStream(
            track.stream_url,
            audio_parameters=audio_q,
            video_parameters=video_q,
            video_flags=MediaStream.Flags.AUTO_DETECT if track.is_video else MediaStream.Flags.IGNORE,
            ffmpeg_parameters=ffmpeg_params,
        )

    async def play_stream(
        self,
        chat_id: int,
        track: Track,
        quality: str = "high",
        eq_preset: str = "flat",
        volume: int = 100,
        seek_sec: int = 0,
    ) -> None:
        stream = self.build_media_stream(
            track, quality=quality, eq_preset=eq_preset, seek_sec=seek_sec
        )
        await self.calls.play(chat_id, stream)
        state = self.queues.get_state(chat_id)
        state.started_at = time.monotonic()
        state.seek_offset = seek_sec
        state.is_paused = False
        if volume != 100:
            try:
                await self.calls.change_volume_call(chat_id, volume)
            except Exception as exc:
                logger.debug("Volume adjust skipped for %s: %s", chat_id, exc)

    async def pause(self, chat_id: int) -> bool:
        await self.calls.pause_stream(chat_id)
        state = self.queues.get_state(chat_id)
        state.is_paused = True
        return True

    async def resume(self, chat_id: int) -> bool:
        await self.calls.resume_stream(chat_id)
        state = self.queues.get_state(chat_id)
        state.is_paused = False
        return True

    async def set_volume(self, chat_id: int, volume: int) -> int:
        clamped = max(1, min(200, volume))
        await self.calls.change_volume_call(chat_id, clamped)
        state = self.queues.get_state(chat_id)
        state.volume = clamped
        return clamped

    async def seek(self, chat_id: int, seconds: int, quality: str = "high") -> Track | None:
        state = self.queues.get_state(chat_id)
        if not state.current or state.current.is_live:
            return None
        target = max(0, min(seconds, max(0, state.current.duration_sec - 2)))
        await self.play_stream(
            chat_id,
            state.current,
            quality=quality,
            eq_preset=state.eq_preset,
            volume=state.volume,
            seek_sec=target,
        )
        return state.current

    async def skip(self, chat_id: int, quality: str = "high") -> Track | None:
        next_track = await self.queues.advance(chat_id, force_skip=True)
        if next_track is None:
            await self.leave(chat_id)
            return None
        state = self.queues.get_state(chat_id)
        await self.play_stream(
            chat_id,
            next_track,
            quality=quality,
            eq_preset=state.eq_preset,
            volume=state.volume,
        )
        return next_track

    async def previous(self, chat_id: int, quality: str = "high") -> Track | None:
        prev_track = await self.queues.previous(chat_id)
        if prev_track is None:
            return None
        state = self.queues.get_state(chat_id)
        await self.play_stream(
            chat_id,
            prev_track,
            quality=quality,
            eq_preset=state.eq_preset,
            volume=state.volume,
        )
        return prev_track

    async def stop(self, chat_id: int) -> None:
        await self.queues.clear(chat_id, keep_current=False)
        await self.leave(chat_id)

    async def leave(self, chat_id: int) -> None:
        try:
            await self.calls.leave_call(chat_id)
        except Exception as exc:
            logger.debug("leave_call ignored for %s: %s", chat_id, exc)
