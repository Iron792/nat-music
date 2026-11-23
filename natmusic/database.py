"""Async persistence layer for Nat Music (SQLite default, zero external setup)."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass(slots=True)
class ChatSettings:
    chat_id: int
    admin_only: bool = False
    vote_skip: bool = True
    vote_threshold: int = 3
    volume: int = 100
    eq_preset: str = "flat"
    auto_play: bool = False
    auto_leave: bool = True
    quality: str = "high"  # studio | high | medium

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Database:
    """Async SQLite database for chat settings, auth users, and saved playlists."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                admin_only INTEGER NOT NULL DEFAULT 0,
                vote_skip INTEGER NOT NULL DEFAULT 1,
                vote_threshold INTEGER NOT NULL DEFAULT 3,
                volume INTEGER NOT NULL DEFAULT 100,
                eq_preset TEXT NOT NULL DEFAULT 'flat',
                auto_play INTEGER NOT NULL DEFAULT 0,
                auto_leave INTEGER NOT NULL DEFAULT 1,
                quality TEXT NOT NULL DEFAULT 'high'
            );

            CREATE TABLE IF NOT EXISTS auth_users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS playlists (
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                tracks_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (owner_id, name)
            );
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call await db.connect() first.")
        return self._conn

    # ── Chat Settings ──────────────────────────────────────────────────────────

    async def get_settings(self, chat_id: int) -> ChatSettings:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return ChatSettings(chat_id=chat_id)
        return ChatSettings(
            chat_id=row["chat_id"],
            admin_only=bool(row["admin_only"]),
            vote_skip=bool(row["vote_skip"]),
            vote_threshold=row["vote_threshold"],
            volume=row["volume"],
            eq_preset=row["eq_preset"],
            auto_play=bool(row["auto_play"]),
            auto_leave=bool(row["auto_leave"]),
            quality=row["quality"],
        )

    async def update_settings(self, chat_id: int, **kwargs: Any) -> ChatSettings:
        current = await self.get_settings(chat_id)
        for key, value in kwargs.items():
            if hasattr(current, key):
                setattr(current, key, value)
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO chat_settings (
                chat_id, admin_only, vote_skip, vote_threshold,
                volume, eq_preset, auto_play, auto_leave, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                admin_only = excluded.admin_only,
                vote_skip = excluded.vote_skip,
                vote_threshold = excluded.vote_threshold,
                volume = excluded.volume,
                eq_preset = excluded.eq_preset,
                auto_play = excluded.auto_play,
                auto_leave = excluded.auto_leave,
                quality = excluded.quality
            """,
            (
                current.chat_id,
                int(current.admin_only),
                int(current.vote_skip),
                current.vote_threshold,
                current.volume,
                current.eq_preset,
                int(current.auto_play),
                int(current.auto_leave),
                current.quality,
            ),
        )
        await conn.commit()
        return current

    # ── Authorized DJs ─────────────────────────────────────────────────────────

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT 1 FROM auth_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cur:
            return (await cur.fetchone()) is not None

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO auth_users (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id),
        )
        await conn.commit()

    async def remove_auth(self, chat_id: int, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "DELETE FROM auth_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await conn.commit()

    async def list_auth(self, chat_id: int) -> list[int]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT user_id FROM auth_users WHERE chat_id = ?", (chat_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [r["user_id"] for r in rows]

    # ── Saved Playlists ────────────────────────────────────────────────────────

    async def get_playlist(self, owner_id: int, name: str = "favorites") -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT tracks_json FROM playlists WHERE owner_id = ? AND name = ?",
            (owner_id, name.lower()),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return []
        return json.loads(row["tracks_json"])

    async def add_to_playlist(
        self, owner_id: int, track: dict[str, Any], name: str = "favorites"
    ) -> list[dict[str, Any]]:
        tracks = await self.get_playlist(owner_id, name)
        if not any(t.get("url") == track.get("url") and track.get("url") for t in tracks):
            tracks.append(track)
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO playlists (owner_id, name, tracks_json) VALUES (?, ?, ?)
            ON CONFLICT(owner_id, name) DO UPDATE SET tracks_json = excluded.tracks_json
            """,
            (owner_id, name.lower(), json.dumps(tracks)),
        )
        await conn.commit()
        return tracks

    async def remove_from_playlist(
        self, owner_id: int, index: int, name: str = "favorites"
    ) -> list[dict[str, Any]]:
        tracks = await self.get_playlist(owner_id, name)
        if 0 <= index < len(tracks):
            tracks.pop(index)
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO playlists (owner_id, name, tracks_json) VALUES (?, ?, ?)
            ON CONFLICT(owner_id, name) DO UPDATE SET tracks_json = excluded.tracks_json
            """,
            (owner_id, name.lower(), json.dumps(tracks)),
        )
        await conn.commit()
        return tracks

    async def list_playlists(self, owner_id: int) -> list[str]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT name FROM playlists WHERE owner_id = ? ORDER BY name", (owner_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [r["name"] for r in rows]
