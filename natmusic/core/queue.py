"""Per-chat queue, loop, shuffle, history, and vote-skip state management."""

from __future__ import annotations

import asyncio
import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopMode(str, Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"

    def next_mode(self) -> "LoopMode":
        order = [LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE]
        return order[(order.index(self) + 1) % len(order)]

    @property
    def label(self) -> str:
        return {
            LoopMode.OFF: "Off",
            LoopMode.TRACK: "Single",
            LoopMode.QUEUE: "Queue",
        }[self]


@dataclass(slots=True)
class Track:
    title: str
    stream_url: str
    webpage_url: str = ""
    duration_sec: int = 0
    duration_str: str = "Live"
    artist: str = "Unknown Artist"
    thumbnail: str = ""
    requester_id: int = 0
    requester_name: str = "Unknown"
    is_video: bool = False
    is_live: bool = False
    source: str = "youtube"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "stream_url": self.stream_url,
            "url": self.webpage_url or self.stream_url,
            "duration_sec": self.duration_sec,
            "duration_str": self.duration_str,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
            "is_video": self.is_video,
            "is_live": self.is_live,
            "source": self.source,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        requester_id: int = 0,
        requester_name: str = "Unknown",
    ) -> "Track":
        return cls(
            title=data.get("title", "Untitled Track"),
            stream_url=data.get("stream_url", data.get("url", "")),
            webpage_url=data.get("url", data.get("webpage_url", "")),
            duration_sec=int(data.get("duration_sec", 0)),
            duration_str=data.get("duration_str", "0:00"),
            artist=data.get("artist", "Unknown Artist"),
            thumbnail=data.get("thumbnail", ""),
            requester_id=requester_id,
            requester_name=requester_name,
            is_video=bool(data.get("is_video", False)),
            is_live=bool(data.get("is_live", False)),
            source=data.get("source", "playlist"),
        )


@dataclass
class ChatQueueState:
    current: Track | None = None
    upcoming: deque[Track] = field(default_factory=deque)
    history: deque[Track] = field(default_factory=lambda: deque(maxlen=25))
    loop_mode: LoopMode = LoopMode.OFF
    is_paused: bool = False
    volume: int = 100
    eq_preset: str = "flat"
    started_at: float = 0.0
    seek_offset: int = 0
    skip_votes: set[int] = field(default_factory=set)
    now_playing_msg_id: int | None = None


class QueueManager:
    """Thread-safe async queue manager isolated per Telegram chat_id."""

    def __init__(self) -> None:
        self._chats: dict[int, ChatQueueState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    def get_state(self, chat_id: int) -> ChatQueueState:
        if chat_id not in self._chats:
            self._chats[chat_id] = ChatQueueState()
        return self._chats[chat_id]

    async def enqueue(
        self, chat_id: int, track: Track, play_next: bool = False
    ) -> tuple[bool, int]:
        """Add track to queue. Returns (started_immediately, 1-based position)."""
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            if state.current is None:
                state.current = track
                state.is_paused = False
                state.seek_offset = 0
                state.skip_votes.clear()
                return True, 0
            if play_next:
                state.upcoming.appendleft(track)
                return False, 1
            state.upcoming.append(track)
            return False, len(state.upcoming)

    async def advance(self, chat_id: int, force_skip: bool = False) -> Track | None:
        """Advance to the next track respecting LoopMode."""
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            prev = state.current
            state.skip_votes.clear()
            state.is_paused = False
            state.seek_offset = 0

            if prev is not None and state.loop_mode == LoopMode.TRACK and not force_skip:
                return prev

            if prev is not None:
                state.history.append(prev)
                if state.loop_mode == LoopMode.QUEUE:
                    state.upcoming.append(prev)

            if state.upcoming:
                state.current = state.upcoming.popleft()
                return state.current

            state.current = None
            return None

    async def previous(self, chat_id: int) -> Track | None:
        """Go back to the previously played track."""
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            if not state.history:
                return None
            if state.current is not None:
                state.upcoming.appendleft(state.current)
            state.current = state.history.pop()
            state.is_paused = False
            state.seek_offset = 0
            state.skip_votes.clear()
            return state.current

    async def shuffle(self, chat_id: int) -> int:
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            items = list(state.upcoming)
            random.shuffle(items)
            state.upcoming = deque(items)
            return len(items)

    async def remove_at(self, chat_id: int, position: int) -> Track | None:
        """Remove 1-based position from upcoming queue."""
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            idx = position - 1
            if idx < 0 or idx >= len(state.upcoming):
                return None
            items = list(state.upcoming)
            removed = items.pop(idx)
            state.upcoming = deque(items)
            return removed

    async def move(self, chat_id: int, src: int, dst: int) -> Track | None:
        """Move track from 1-based src position to 1-based dst position."""
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            items = list(state.upcoming)
            s_idx, d_idx = src - 1, dst - 1
            if not (0 <= s_idx < len(items)) or not (0 <= d_idx < len(items)):
                return None
            track = items.pop(s_idx)
            items.insert(d_idx, track)
            state.upcoming = deque(items)
            return track

    async def clear(self, chat_id: int, keep_current: bool = True) -> int:
        async with self._lock(chat_id):
            state = self.get_state(chat_id)
            count = len(state.upcoming)
            state.upcoming.clear()
            if not keep_current:
                state.current = None
                state.is_paused = False
                state.skip_votes.clear()
            return count

    def active_chats(self) -> list[int]:
        return [cid for cid, st in self._chats.items() if st.current is not None]
