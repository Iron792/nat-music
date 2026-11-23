"""Queue management & saved playlist commands: /queue, /shuffle, /loop, /remove, /move, /clear, /playlist."""

from __future__ import annotations

import html

from pyrogram import Client, filters
from pyrogram.types import Message

from natmusic.core.clients import runtime
from natmusic.core.queue import LoopMode, Track
from natmusic.plugins.helpers import can_control, ensure_assistant_in_chat, format_queue_page, send_now_playing
from natmusic.ui.keyboards import queue_keyboard


def register(app: Client) -> None:
    @app.on_message(filters.command(["queue", "q"]) & filters.group)
    async def cmd_queue(_: Client, message: Message) -> None:
        state = runtime.queues.get_state(message.chat.id)
        text, total_pages = format_queue_page(state, page=1)
        await message.reply_text(
            text,
            reply_markup=queue_keyboard(1, total_pages),
            disable_web_page_preview=True,
        )

    @app.on_message(filters.command("shuffle") & filters.group)
    async def cmd_shuffle(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await can_control(client, message.chat.id, uid):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        count = await runtime.queues.shuffle(message.chat.id)
        await message.reply_text(f"🔀 Shuffled <b>{count}</b> upcoming track(s).")

    @app.on_message(filters.command("loop") & filters.group)
    async def cmd_loop(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await can_control(client, message.chat.id, uid):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        state = runtime.queues.get_state(message.chat.id)
        if len(message.command) >= 2:
            arg = message.command[1].lower()
            mapping = {"off": LoopMode.OFF, "track": LoopMode.TRACK, "single": LoopMode.TRACK, "queue": LoopMode.QUEUE, "all": LoopMode.QUEUE}
            if arg in mapping:
                state.loop_mode = mapping[arg]
            else:
                await message.reply_text("💡 Usage: <code>/loop [off|track|queue]</code>")
                return
        else:
            state.loop_mode = state.loop_mode.next_mode()
        await message.reply_text(f"🔁 Loop mode set to <b>{state.loop_mode.label}</b>.")

    @app.on_message(filters.command("remove") & filters.group)
    async def cmd_remove(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await can_control(client, message.chat.id, uid):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if len(message.command) < 2 or not message.command[1].isdigit():
            await message.reply_text("💡 Usage: <code>/remove [queue_number]</code>")
            return
        removed = await runtime.queues.remove_at(message.chat.id, int(message.command[1]))
        if removed:
            await message.reply_text(f"🗑 Removed <b>{html.escape(removed.title)}</b> from queue.")
        else:
            await message.reply_text("❌ Invalid queue position.")

    @app.on_message(filters.command("move") & filters.group)
    async def cmd_move(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await can_control(client, message.chat.id, uid):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if len(message.command) < 3 or not (message.command[1].isdigit() and message.command[2].isdigit()):
            await message.reply_text("💡 Usage: <code>/move [from] [to]</code>")
            return
        moved = await runtime.queues.move(message.chat.id, int(message.command[1]), int(message.command[2]))
        if moved:
            await message.reply_text(f"↕️ Moved <b>{html.escape(moved.title)}</b> to position #{message.command[2]}.")
        else:
            await message.reply_text("❌ Invalid queue positions.")

    @app.on_message(filters.command("clear") & filters.group)
    async def cmd_clear(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await can_control(client, message.chat.id, uid):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        cleared = await runtime.queues.clear(message.chat.id, keep_current=True)
        await message.reply_text(f"🧹 Cleared <b>{cleared}</b> upcoming track(s).")

    @app.on_message(filters.command(["playlist", "pl"]))
    async def cmd_playlist(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        uid = message.from_user.id
        uname = message.from_user.first_name or "User"
        args = message.command[1:]

        if not args:
            tracks = await runtime.db.get_playlist(uid)
            if not tracks:
                await message.reply_text(
                    "❤️ Your saved playlist is empty.\nTap <b>❤️ Save</b> on any Now-Playing card to add tracks!"
                )
                return
            lines = ["❤️ <b>Your Saved Favorites</b>\n"]
            for i, t in enumerate(tracks[:15], start=1):
                lines.append(f"<b>{i}.</b> {html.escape(t.get('title', 'Track'))} <code>[{t.get('duration_str', '0:00')}]</code>")
            lines.append("\nRun <code>/playlist play</code> in a group to queue all favorites!")
            await message.reply_text("\n".join(lines))
            return

        sub = args[0].lower()
        if sub == "play" and message.chat and message.chat.type.name != "PRIVATE":
            tracks_data = await runtime.db.get_playlist(uid)
            if not tracks_data:
                await message.reply_text("❤️ Your saved playlist is empty.")
                return
            join_err = await ensure_assistant_in_chat(message.chat.id)
            if join_err:
                await message.reply_text(f"⚠️ {join_err}")
                return
            settings = await runtime.db.get_settings(message.chat.id)
            loaded = [Track.from_dict(d, requester_id=uid, requester_name=uname) for d in tracks_data]
            started_now = False
            for tr in loaded:
                started, _ = await runtime.queues.enqueue(message.chat.id, tr)
                if started:
                    started_now = True
            if started_now and runtime.player:
                await runtime.player.play_stream(
                    message.chat.id,
                    loaded[0],
                    quality=settings.quality,
                    eq_preset=settings.eq_preset,
                    volume=settings.volume,
                )
                await send_now_playing(message.chat.id, loaded[0])
            await message.reply_text(f"❤️ Queued <b>{len(loaded)}</b> track(s) from your favorites!")
        elif sub == "del" and len(args) >= 2 and args[1].isdigit():
            updated = await runtime.db.remove_from_playlist(uid, int(args[1]) - 1)
            await message.reply_text(f"🗑 Removed track. <b>{len(updated)}</b> track(s) remaining.")
        else:
            await message.reply_text("💡 Usage: <code>/playlist</code> | <code>/playlist play</code> | <code>/playlist del [num]</code>")
