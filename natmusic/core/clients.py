"""Central runtime container for Pyrogram Bot, Assistant, PyTgCalls, DB, and Player."""

from __future__ import annotations

import logging
import time

from pyrogram import Client
from pytgcalls import PyTgCalls

from natmusic.config import config
from natmusic.core.player import NatPlayer
from natmusic.core.queue import QueueManager
from natmusic.database import Database

logger = logging.getLogger("natmusic.clients")


class NatRuntime:
    def __init__(self) -> None:
        self.boot_time = time.monotonic()
        self.db = Database(config.sqlite_path)
        self.queues = QueueManager()

        self.bot = Client(
            name="NatMusicBot",
            api_id=config.api_id,
            api_hash=config.api_hash,
            bot_token=config.bot_token,
            in_memory=True,
        )
        self.assistant = Client(
            name="NatMusicAssistant",
            api_id=config.api_id,
            api_hash=config.api_hash,
            session_string=config.string_session,
            in_memory=True,
        )
        self.calls = PyTgCalls(self.assistant)
        self.player: NatPlayer | None = None

    async def start(self) -> None:
        config.validate()
        await self.db.connect()
        await self.bot.start()
        await self.assistant.start()
        await self.calls.start()
        logger.info("Nat Music clients started successfully.")

    async def stop(self) -> None:
        for client in (self.bot, self.assistant):
            try:
                await client.stop()
            except Exception:
                pass
        await self.db.close()
        logger.info("Nat Music stopped cleanly.")


runtime = NatRuntime()
