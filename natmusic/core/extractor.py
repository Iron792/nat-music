"""Async media extractor using yt-dlp, plus curated live radio presets."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from natmusic.core.queue import Track

RADIO_STATIONS: dict[str, dict[str, str]] = {
    "lofi": {
        "title": "Lofi Girl — Beats to Relax/Study To",
        "artist": "Lofi Records Radio",
        "url": "https://play.streamafrica.net/lofiradio",
    },
    "chillhop": {
        "title": "Chillhop Music — 24/7 Chill Beats",
        "artist": "Chillhop Radio",
        "url": "https://streams.fluxfm.de/Chillhop/mp3-320/streams.fluxfm.de/",
    },
    "synthwave": {
        "title": "Nightride FM — Synthwave & Retrowave",
        "artist": "Nightride FM",
        "url": "https://stream.nightride.fm/nightride.m4a",
    },
    "jazz": {
        "title": "Smooth Jazz 24/7",
        "artist": "SmoothJazz.com",
        "url": "https://smoothjazz.cdnstream1.com/2585_128.mp3",
    },
    "bollywood": {
        "title": "Bollywood Evergreen Hits",
        "artist": "Hindi Radio",
        "url": "https://stream.zeno.fm/r2gn1s4302zuv",
    },
}

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def format_duration(seconds: int | float | None) -> str:
    if not seconds or seconds <= 0:
        return "Live"
    total = int(seconds)
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _extract_sync(query: str, video: bool = False) -> list[dict[str, Any]]:
    is_url = bool(_URL_RE.match(query.strip()))
    search_target = query.strip() if is_url else f"ytsearch1:{query.strip()}"

    fmt = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best"
        if video
        else "bestaudio[ext=m4a]/bestaudio/best"
    )
    ydl_opts: dict[str, Any] = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": False,
        "playlistend": 15,
        "default_search": "ytsearch",
        "source_address": "0.0.0.0",
    }

    import yt_dlp

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=False)
        if not info:
            return []
        entries = info.get("entries")
        if entries is not None:
            return [e for e in entries if e]
        return [info]


async def resolve_query(
    query: str,
    requester_id: int,
    requester_name: str,
    video: bool = False,
    duration_limit_min: int = 180,
) -> list[Track]:
    """Resolve a search query or URL into one or more playable Track objects."""
    raw_entries = await asyncio.to_thread(_extract_sync, query, video)
    tracks: list[Track] = []
    max_sec = duration_limit_min * 60

    for entry in raw_entries:
        stream_url = entry.get("url")
        if not stream_url and entry.get("requested_formats"):
            stream_url = entry["requested_formats"][0].get("url")
        if not stream_url:
            continue

        is_live = bool(entry.get("is_live"))
        duration = int(entry.get("duration") or 0)
        if not is_live and max_sec > 0 and duration > max_sec:
            continue

        tracks.append(
            Track(
                title=entry.get("title") or "Untitled Track",
                stream_url=stream_url,
                webpage_url=entry.get("webpage_url") or query,
                duration_sec=duration,
                duration_str="Live" if is_live else format_duration(duration),
                artist=entry.get("uploader") or entry.get("artist") or "YouTube",
                thumbnail=entry.get("thumbnail") or "",
                requester_id=requester_id,
                requester_name=requester_name,
                is_video=video,
                is_live=is_live,
                source=entry.get("extractor_key", "youtube").lower(),
            )
        )
    return tracks
