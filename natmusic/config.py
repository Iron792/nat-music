"""Typed environment configuration for Nat Music."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    out: list[int] = []
    for part in value.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


@dataclass(slots=True)
class Config:
    api_id: int = field(default_factory=lambda: int(os.getenv("API_ID", "0")))
    api_hash: str = field(default_factory=lambda: os.getenv("API_HASH", ""))
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    string_session: str = field(default_factory=lambda: os.getenv("STRING_SESSION", ""))
    owner_ids: list[int] = field(default_factory=lambda: _parse_int_list(os.getenv("OWNER_IDS")))
    log_chat_id: int | None = field(
        default_factory=lambda: int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID", "").lstrip("-").isdigit() else None
    )

    bot_name: str = field(default_factory=lambda: os.getenv("BOT_NAME", "Nat Music"))
    support_chat: str = field(default_factory=lambda: os.getenv("SUPPORT_CHAT", ""))
    updates_channel: str = field(default_factory=lambda: os.getenv("UPDATES_CHANNEL", ""))

    sqlite_path: Path = field(default_factory=lambda: Path(os.getenv("SQLITE_PATH", "data/nat_music.db")))
    mongo_url: str = field(default_factory=lambda: os.getenv("MONGO_URL", ""))
    downloads_dir: Path = field(default_factory=lambda: Path(os.getenv("DOWNLOADS_DIR", "downloads")))

    duration_limit_min: int = field(default_factory=lambda: int(os.getenv("DURATION_LIMIT_MIN", "180")))
    default_volume: int = field(default_factory=lambda: max(1, min(200, int(os.getenv("DEFAULT_VOLUME", "100")))))
    auto_leave_minutes: int = field(default_factory=lambda: int(os.getenv("AUTO_LEAVE_MINUTES", "10")))
    vote_skip_threshold: int = field(default_factory=lambda: max(1, int(os.getenv("VOTE_SKIP_THRESHOLD", "3"))))
    use_thumbnail_cards: bool = field(default_factory=lambda: _parse_bool(os.getenv("USE_THUMBNAIL_CARDS"), True))

    def validate(self) -> None:
        missing = []
        if not self.api_id:
            missing.append("API_ID")
        if not self.api_hash:
            missing.append("API_HASH")
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.string_session:
            missing.append("STRING_SESSION")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill in your Telegram credentials."
            )
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)


config = Config()
