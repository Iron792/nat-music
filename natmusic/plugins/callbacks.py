"""Unified inline callback router for Now-Playing, Queue, EQ, Settings, and Help."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import CallbackQuery

from natmusic.config import config
from natmusic.core.clients import runtime
from natmusic.core.player import EQ_PRESETS
from natmusic.plugins.helpers import HELP_TEXTS, can_control, format_queue_page, is_admin_or_auth, send_now_playing
from natmusic.ui.cards import format_now_playing_caption
from natmusic.ui.keyboards import (
    eq_keyboard,
    help_keyboard,
    now_playing_keyboard,
    queue_keyboard,
    settings_keyboard,
    volume_keyboard,
)


def register(app: Client) -> None:
    @app.on_callback_query()
    async def on_callback(client: Client, query: CallbackQuery) -> None:
        data = query.data or ""
        if not query.message or not query.from_user:
            await query.answer()
            return

        chat_id = query.message.chat.id
        user_id = query.from_user.id

        # ── Help Tabs ──────────────────────────────────────────────────────────
        if data.startswith("help:tab:"):
            tab = data.split(":", 2)[2]
            text = HELP_TEXTS.get(tab, HELP_TEXTS["playback"])
            await query.message.edit_text(
                text,
                reply_markup=help_keyboard(tab),
                disable_web_page_preview=True,
            )
            await query.answer()
            return

        if data == "np:close":
            await query.message.delete()
            await query.answer()
            return

        if data == "q:noop":
            await query.answer()
            return

        # ── Settings Callbacks (Admin/Auth only) ───────────────────────────────
        if data.startswith("set:"):
            if not await is_admin_or_auth(client, chat_id, user_id):
                await query.answer("🔒 Only admins or authorized DJs can change settings.", show_alert=True)
                return
            parts = data.split(":")
            action, key = parts[1], parts[2]
            settings = await runtime.db.get_settings(chat_id)
            if action == "toggle":
                new_val = not getattr(settings, key)
                settings = await runtime.db.update_settings(chat_id, **{key: new_val})
            elif action == "cycle" and key == "quality":
                order = ["medium", "high", "studio"]
                nxt = order[(order.index(settings.quality) + 1) % len(order)] if settings.quality in order else "high"
                settings = await runtime.db.update_settings(chat_id, quality=nxt)
            await query.message.edit_reply_markup(settings_keyboard(settings))
            await query.answer("Settings updated!")
            return

        # ── Queue Browser Callbacks ────────────────────────────────────────────
        if data.startswith("q:page:") or data.startswith("np:queue:"):
            page = int(data.split(":")[-1])
            state = runtime.queues.get_state(chat_id)
            text, total_pages = format_queue_page(state, page=page)
            if query.message.photo:
                await query.message.edit_caption(text, reply_markup=queue_keyboard(page, total_pages))
            else:
                await query.message.edit_text(
                    text, reply_markup=queue_keyboard(page, total_pages), disable_web_page_preview=True
                )
            await query.answer()
            return

        if data == "q:clear":
            if not await can_control(client, chat_id, user_id):
                await query.answer("🔒 Admin-Only mode is enabled.", show_alert=True)
                return
            cleared = await runtime.queues.clear(chat_id, keep_current=True)
            state = runtime.queues.get_state(chat_id)
            text, total_pages = format_queue_page(state, page=1)
            if query.message.photo:
                await query.message.edit_caption(text, reply_markup=queue_keyboard(1, total_pages))
            else:
                await query.message.edit_text(text, reply_markup=queue_keyboard(1, total_pages))
            await query.answer(f"Cleared {cleared} track(s).")
            return

        # ── Save to Favorites (Personal, available to anyone) ──────────────────
        if data == "np:save":
            state = runtime.queues.get_state(chat_id)
            if not state.current:
                await query.answer("Nothing is playing right now.", show_alert=True)
                return
            tracks = await runtime.db.add_to_playlist(user_id, state.current.to_dict())
            await query.answer(f"❤️ Saved to your Favorites ({len(tracks)} total)!", show_alert=True)
            return

        # ── Player & EQ Callbacks ──────────────────────────────────────────────
        state = runtime.queues.get_state(chat_id)
        settings = await runtime.db.get_settings(chat_id)

        if data == "np:back":
            caption = format_now_playing_caption(state, bot_name=config.bot_name)
            markup = now_playing_keyboard(state)
            if query.message.photo:
                await query.message.edit_caption(caption, reply_markup=markup)
            else:
                await query.message.edit_text(caption, reply_markup=markup, disable_web_page_preview=True)
            await query.answer()
            return

        if data == "np:vol_menu":
            await query.message.edit_reply_markup(volume_keyboard(state.volume))
            await query.answer()
            return

        if data == "np:eq_menu":
            await query.message.edit_reply_markup(eq_keyboard(state.eq_preset))
            await query.answer()
            return

        # Permission check for mutating player controls
        if not await can_control(client, chat_id, user_id):
            await query.answer("🔒 Admin-Only mode is enabled.", show_alert=True)
            return

        if data == "np:toggle" and runtime.player:
            if state.is_paused:
                await runtime.player.resume(chat_id)
                await query.answer("▶️ Resumed")
            else:
                await runtime.player.pause(chat_id)
                await query.answer("⏸ Paused")
            caption = format_now_playing_caption(state, bot_name=config.bot_name)
            markup = now_playing_keyboard(state)
            if query.message.photo:
                await query.message.edit_caption(caption, reply_markup=markup)
            else:
                await query.message.edit_text(caption, reply_markup=markup, disable_web_page_preview=True)
            return

        if data == "np:skip" and runtime.player:
            next_tr = await runtime.player.skip(chat_id, quality=settings.quality)
            await query.answer("⏭ Skipped")
            if next_tr:
                await send_now_playing(chat_id, next_tr)
            else:
                await query.message.delete()
            return

        if data == "np:prev" and runtime.player:
            prev_tr = await runtime.player.previous(chat_id, quality=settings.quality)
            if prev_tr:
                await query.answer("⏮ Playing previous track")
                await send_now_playing(chat_id, prev_tr)
            else:
                await query.answer("No previous track in history.", show_alert=True)
            return

        if data == "np:stop" and runtime.player:
            await runtime.player.stop(chat_id)
            await query.answer("⏹ Stopped")
            await query.message.delete()
            return

        if data == "np:shuffle":
            count = await runtime.queues.shuffle(chat_id)
            await query.answer(f"🔀 Shuffled {count} track(s)")
            await query.message.edit_reply_markup(now_playing_keyboard(state))
            return

        if data == "np:loop":
            state.loop_mode = state.loop_mode.next_mode()
            await query.answer(f"🔁 Loop: {state.loop_mode.label}")
            caption = format_now_playing_caption(state, bot_name=config.bot_name)
            markup = now_playing_keyboard(state)
            if query.message.photo:
                await query.message.edit_caption(caption, reply_markup=markup)
            else:
                await query.message.edit_text(caption, reply_markup=markup, disable_web_page_preview=True)
            return

        if data.startswith("np:vol:") and runtime.player:
            vol = int(data.split(":")[-1])
            clamped = await runtime.player.set_volume(chat_id, vol)
            await runtime.db.update_settings(chat_id, volume=clamped)
            await query.answer(f"🔊 Volume: {clamped}%")
            await query.message.edit_reply_markup(volume_keyboard(clamped))
            return

        if data.startswith("np:vol_step:") and runtime.player:
            delta = int(data.split(":")[-1])
            clamped = await runtime.player.set_volume(chat_id, state.volume + delta)
            await runtime.db.update_settings(chat_id, volume=clamped)
            await query.answer(f"🔊 Volume: {clamped}%")
            await query.message.edit_reply_markup(volume_keyboard(clamped))
            return

        if data.startswith("eq:set:"):
            preset = data.split(":")[-1]
            if preset in EQ_PRESETS:
                state.eq_preset = preset
                await runtime.db.update_settings(chat_id, eq_preset=preset)
                await query.answer(f"🎛 EQ: {EQ_PRESETS[preset]['label']}")
                await query.message.edit_reply_markup(eq_keyboard(preset))
            else:
                await query.answer("Unknown EQ preset.")
