"""Settings, EQ, auth DJs, /start, /help, /np, /ping, and /stats commands."""

from __future__ import annotations

import html
import time

import psutil
from pyrogram import Client, filters
from pyrogram.types import Message

from natmusic.config import config
from natmusic.core.clients import runtime
from natmusic.core.extractor import format_duration
from natmusic.core.player import EQ_PRESETS
from natmusic.plugins.helpers import HELP_TEXTS, is_admin_or_auth, send_now_playing
from natmusic.ui.keyboards import eq_keyboard, help_keyboard, settings_keyboard, start_keyboard


def register(app: Client) -> None:
    @app.on_message(filters.command("start"))
    async def cmd_start(client: Client, message: Message) -> None:
        me = await client.get_me()
        user_name = html.escape(message.from_user.first_name) if message.from_user else "there"
        text = (
            f"🎧 <b>Hey {user_name}, welcome to {html.escape(config.bot_name)}!</b>\n\n"
            "I stream crisp audio & video into Telegram group voice chats with "
            "glassmorphic Now-Playing cards, interactive controls, live EQ presets, "
            "24/7 radio, and saved playlists.\n\n"
            "Add me to a group, promote me to admin, and type <code>/play song name</code>."
        )
        await message.reply_text(
            text,
            reply_markup=start_keyboard(
                me.username or "",
                support_chat=config.support_chat,
                updates_channel=config.updates_channel,
            ),
            disable_web_page_preview=True,
        )

    @app.on_message(filters.command("help"))
    async def cmd_help(_: Client, message: Message) -> None:
        await message.reply_text(
            HELP_TEXTS["playback"],
            reply_markup=help_keyboard("playback"),
            disable_web_page_preview=True,
        )

    @app.on_message(filters.command(["np", "nowplaying"]) & filters.group)
    async def cmd_np(_: Client, message: Message) -> None:
        state = runtime.queues.get_state(message.chat.id)
        if not state.current:
            await message.reply_text("ℹ️ Nothing is currently playing.")
            return
        await send_now_playing(message.chat.id)

    @app.on_message(filters.command("settings") & filters.group)
    async def cmd_settings(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await is_admin_or_auth(client, message.chat.id, uid):
            await message.reply_text("🔒 Only group admins or authorized DJs can change settings.")
            return
        settings = await runtime.db.get_settings(message.chat.id)
        await message.reply_text(
            f"⚙️ <b>{html.escape(config.bot_name)} — Group Settings</b>\n\n"
            "Tap any option below to toggle or cycle:",
            reply_markup=settings_keyboard(settings),
        )

    @app.on_message(filters.command("eq") & filters.group)
    async def cmd_eq(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        uid = message.from_user.id if message.from_user else 0
        if not await is_admin_or_auth(client, chat_id, uid):
            await message.reply_text("🔒 Only group admins or authorized DJs can change EQ.")
            return
        settings = await runtime.db.get_settings(chat_id)
        if len(message.command) >= 2:
            preset = message.command[1].lower()
            if preset not in EQ_PRESETS:
                valid = ", ".join(EQ_PRESETS.keys())
                await message.reply_text(f"❌ Invalid preset. Choose from: <code>{valid}</code>")
                return
            await runtime.db.update_settings(chat_id, eq_preset=preset)
            state = runtime.queues.get_state(chat_id)
            state.eq_preset = preset
            await message.reply_text(
                f"🎛 Equalizer set to <b>{EQ_PRESETS[preset]['label']}</b> "
                "(applied immediately on next seek/track)."
            )
            return

        await message.reply_text(
            "🎛 <b>Select an Equalizer Preset:</b>",
            reply_markup=eq_keyboard(settings.eq_preset),
        )

    @app.on_message(filters.command("auth") & filters.group)
    async def cmd_auth(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await is_admin_or_auth(client, message.chat.id, uid):
            await message.reply_text("🔒 Only admins can authorize DJs.")
            return
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text("💡 Reply to a user's message with <code>/auth</code>.")
            return
        target = message.reply_to_message.from_user
        await runtime.db.add_auth(message.chat.id, target.id)
        await message.reply_text(f"✅ <b>{html.escape(target.first_name)}</b> is now an authorized DJ.")

    @app.on_message(filters.command("unauth") & filters.group)
    async def cmd_unauth(client: Client, message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not await is_admin_or_auth(client, message.chat.id, uid):
            await message.reply_text("🔒 Only admins can revoke DJ permissions.")
            return
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text("💡 Reply to a user's message with <code>/unauth</code>.")
            return
        target = message.reply_to_message.from_user
        await runtime.db.remove_auth(message.chat.id, target.id)
        await message.reply_text(f"🚫 Revoked DJ permissions from <b>{html.escape(target.first_name)}</b>.")

    @app.on_message(filters.command("ping"))
    async def cmd_ping(_: Client, message: Message) -> None:
        t0 = time.monotonic()
        msg = await message.reply_text("🏓 Pinging...")
        ms = int((time.monotonic() - t0) * 1000)
        uptime = format_duration(time.monotonic() - runtime.boot_time)
        await msg.edit_text(f"🏓 <b>Pong!</b> <code>{ms}ms</code>\n⏱ <b>Uptime:</b> <code>{uptime}</code>")

    @app.on_message(filters.command("stats"))
    async def cmd_stats(_: Client, message: Message) -> None:
        active_vcs = len(runtime.queues.active_chats())
        uptime = format_duration(time.monotonic() - runtime.boot_time)
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await message.reply_text(
            f"📊 <b>{html.escape(config.bot_name)} Stats</b>\n\n"
            f"🎙 <b>Active Voice Chats:</b> <code>{active_vcs}</code>\n"
            f"⏱ <b>Uptime:</b> <code>{uptime}</code>\n"
            f"🖥 <b>CPU:</b> <code>{cpu}%</code>  |  🧠 <b>RAM:</b> <code>{ram}%</code>"
        )
