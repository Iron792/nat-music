"""Main entrypoint for Nat Music Telegram VC Bot."""

from __future__ import annotations

import asyncio
import logging

from pytgcalls import idle

from natmusic.core.clients import runtime
from natmusic.core.player import NatPlayer
from natmusic.plugins import callbacks, playback, queue_cmd, settings
from natmusic.plugins.helpers import send_now_playing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("natmusic")


async def _on_queue_ended(chat_id: int) -> None:
    try:
        await runtime.bot.send_message(
            chat_id,
            "⏹ <b>Queue finished.</b> Left the voice chat.",
        )
    except Exception:
        pass


async def main() -> None:
    runtime.player = NatPlayer(
        calls=runtime.calls,
        queues=runtime.queues,
        on_track_started=send_now_playing,
        on_queue_ended=_on_queue_ended,
    )

    playback.register(runtime.bot)
    queue_cmd.register(runtime.bot)
    settings.register(runtime.bot)
    callbacks.register(runtime.bot)

    await runtime.start()
    logger.info("Nat Music is online and ready.")
    try:
        await idle()
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
