"""Playback commands: /play, /vplay, /pplay, /radio, /pause, /resume, /skip, /prev, /stop, /seek, /volume."""

from __future__ import annotations

import html
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

from natmusic.config import config
from natmusic.core.clients import runtime
from natmusic.core.extractor import RADIO_STATIONS, resolve_query
from natmusic.core.queue import Track
from natmusic.plugins.helpers import (
    can_control,
    ensure_assistant_in_chat,
    is_admin_or_auth,
    send_now_playing,
)


def _requester_info(message: Message) -> tuple[int, str]:
    user = message.from_user
    if user:
        return user.id, user.first_name or "User"
    if message.sender_chat:
        return message.sender_chat.id, message.sender_chat.title or "Channel"
    return 0, "Anonymous"


async def _handle_play(client: Client, message: Message, video: bool = False, play_next: bool = False) -> None:
    if not message.chat:
        return
    chat_id = message.chat.id
    req_id, req_name = _requester_info(message)

    join_err = await ensure_assistant_in_chat(chat_id)
    if join_err:
        await message.reply_text(f"⚠️ {join_err}")
        return

    query = " ".join(message.command[1:]).strip()
    tracks: list[Track] = []

    # Support replying to a Telegram audio, voice, or video file
    replied = message.reply_to_message
    if not query and replied and (replied.audio or replied.voice or replied.video or replied.document):
        media = replied.audio or replied.voice or replied.video or replied.document
        status_msg = await message.reply_text("📥 <b>Downloading Telegram media...</b>")
        file_path = await replied.download(file_name=str(config.downloads_dir / f"{chat_id}_{media.file_unique_id}"))
        title = getattr(media, "title", None) or getattr(media, "file_name", None) or "Telegram Media"
        artist = getattr(media, "performer", None) or "Telegram"
        dur = int(getattr(media, "duration", 0) or 0)
        from natmusic.core.extractor import format_duration

        tracks = [
            Track(
                title=Path(title).stem if "." in title else title,
                stream_url=file_path,
                duration_sec=dur,
                duration_str=format_duration(dur),
                artist=artist,
                requester_id=req_id,
                requester_name=req_name,
                is_video=bool(replied.video or video),
                source="telegram",
            )
        ]
        await status_msg.delete()
    elif query:
        status_msg = await message.reply_text("🔎 <b>Searching & resolving stream...</b>")
        try:
            tracks = await resolve_query(
                query,
                requester_id=req_id,
                requester_name=req_name,
                video=video,
                duration_limit_min=config.duration_limit_min,
            )
        except Exception as exc:
            await status_msg.edit_text(f"❌ Could not resolve media: <code>{html.escape(str(exc)[:180])}</code>")
            return
        await status_msg.delete()
    else:
        await message.reply_text(
            "💡 Usage: <code>/play song name or link</code> (or reply to an audio/video message)."
        )
        return

    if not tracks:
        await message.reply_text("❌ No playable tracks found (or track exceeds duration limit).")
        return

    settings = await runtime.db.get_settings(chat_id)
    state = runtime.queues.get_state(chat_id)
    state.eq_preset = settings.eq_preset
    state.volume = settings.volume

    started_now = False
    first_pos = 0
    for idx, tr in enumerate(tracks):
        started, pos = await runtime.queues.enqueue(chat_id, tr, play_next=play_next and idx == 0)
        if started:
            started_now = True
        elif first_pos == 0:
            first_pos = pos

    if started_now and runtime.player:
        await runtime.player.play_stream(
            chat_id,
            tracks[0],
            quality=settings.quality,
            eq_preset=settings.eq_preset,
            volume=settings.volume,
        )
        await send_now_playing(chat_id, tracks[0])
        if len(tracks) > 1:
            await message.reply_text(f"➕ Added <b>{len(tracks) - 1}</b> more playlist track(s) to the queue.")
    else:
        if len(tracks) == 1:
            await message.reply_text(
                f"➕ <b>Queued at #{first_pos}:</b> {html.escape(tracks[0].title)} "
                f"<code>[{tracks[0].duration_str}]</code>"
            )
        else:
            await message.reply_text(f"➕ Added <b>{len(tracks)}</b> tracks to the queue.")


def register(app: Client) -> None:
    @app.on_message(filters.command(["play", "p"]) & filters.group)
    async def cmd_play(client: Client, message: Message) -> None:
        await _handle_play(client, message, video=False, play_next=False)

    @app.on_message(filters.command(["vplay", "vp"]) & filters.group)
    async def cmd_vplay(client: Client, message: Message) -> None:
        await _handle_play(client, message, video=True, play_next=False)

    @app.on_message(filters.command(["pplay", "playnext"]) & filters.group)
    async def cmd_pplay(client: Client, message: Message) -> None:
        await _handle_play(client, message, video=False, play_next=True)

    @app.on_message(filters.command("radio") & filters.group)
    async def cmd_radio(_: Client, message: Message) -> None:
        args = message.command[1:]
        if not args:
            stations = "\n".join(
                f"• <code>/radio {k}</code> — {v['title']}" for k, v in RADIO_STATIONS.items()
            )
            await message.reply_text(f"📻 <b>Curated 24/7 Live Radio Stations</b>\n\n{stations}")
            return

        key = args[0].lower()
        station = RADIO_STATIONS.get(key)
        if not station:
            await message.reply_text(
                f"❌ Unknown station <code>{html.escape(key)}</code>. Run <code>/radio</code> to see available stations."
            )
            return

        chat_id = message.chat.id
        join_err = await ensure_assistant_in_chat(chat_id)
        if join_err:
            await message.reply_text(f"⚠️ {join_err}")
            return

        req_id, req_name = _requester_info(message)
        track = Track(
            title=station["title"],
            stream_url=station["url"],
            webpage_url=station["url"],
            duration_sec=0,
            duration_str="Live",
            artist=station["artist"],
            requester_id=req_id,
            requester_name=req_name,
            is_live=True,
            source="radio",
        )
        settings = await runtime.db.get_settings(chat_id)
        started, pos = await runtime.queues.enqueue(chat_id, track)
        if started and runtime.player:
            await runtime.player.play_stream(
                chat_id, track, quality=settings.quality, eq_preset=settings.eq_preset, volume=settings.volume
            )
            await send_now_playing(chat_id, track)
        else:
            await message.reply_text(f"📻 <b>Radio queued at #{pos}:</b> {html.escape(track.title)}")

    @app.on_message(filters.command("pause") & filters.group)
    async def cmd_pause(client: Client, message: Message) -> None:
        req_id, _ = _requester_info(message)
        if not await can_control(client, message.chat.id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if runtime.player:
            await runtime.player.pause(message.chat.id)
            await message.reply_text("⏸ <b>Playback paused.</b>")

    @app.on_message(filters.command("resume") & filters.group)
    async def cmd_resume(client: Client, message: Message) -> None:
        req_id, _ = _requester_info(message)
        if not await can_control(client, message.chat.id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if runtime.player:
            await runtime.player.resume(message.chat.id)
            await message.reply_text("▶️ <b>Playback resumed.</b>")

    @app.on_message(filters.command(["skip", "next"]) & filters.group)
    async def cmd_skip(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        req_id, _ = _requester_info(message)
        state = runtime.queues.get_state(chat_id)
        if not state.current:
            await message.reply_text("ℹ️ Nothing is currently playing.")
            return

        settings = await runtime.db.get_settings(chat_id)
        is_privileged = await is_admin_or_auth(client, chat_id, req_id) or (
            state.current.requester_id == req_id
        )

        if not is_privileged:
            if settings.admin_only:
                await message.reply_text("🔒 Only admins or authorized DJs can skip right now.")
                return
            if settings.vote_skip:
                state.skip_votes.add(req_id)
                votes = len(state.skip_votes)
                if votes < settings.vote_threshold:
                    await message.reply_text(
                        f"🗳 <b>Vote Skip:</b> {votes}/{settings.vote_threshold} votes to skip."
                    )
                    return

        if runtime.player:
            next_track = await runtime.player.skip(chat_id, quality=settings.quality)
            if next_track:
                await send_now_playing(chat_id, next_track)
            else:
                await message.reply_text("⏹ <b>Queue finished.</b> Left the voice chat.")

    @app.on_message(filters.command(["prev", "previous"]) & filters.group)
    async def cmd_prev(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        req_id, _ = _requester_info(message)
        if not await can_control(client, chat_id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        settings = await runtime.db.get_settings(chat_id)
        if runtime.player:
            prev_track = await runtime.player.previous(chat_id, quality=settings.quality)
            if prev_track:
                await send_now_playing(chat_id, prev_track)
            else:
                await message.reply_text("ℹ️ No previous track in history.")

    @app.on_message(filters.command(["stop", "end"]) & filters.group)
    async def cmd_stop(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        req_id, _ = _requester_info(message)
        if not await can_control(client, chat_id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if runtime.player:
            await runtime.player.stop(chat_id)
            await message.reply_text("⏹ <b>Stopped playback and cleared the queue.</b>")

    @app.on_message(filters.command("seek") & filters.group)
    async def cmd_seek(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        req_id, _ = _requester_info(message)
        if not await can_control(client, chat_id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if len(message.command) < 2 or not message.command[1].isdigit():
            await message.reply_text("💡 Usage: <code>/seek 60</code> (seconds)")
            return
        seconds = int(message.command[1])
        settings = await runtime.db.get_settings(chat_id)
        if runtime.player:
            tr = await runtime.player.seek(chat_id, seconds, quality=settings.quality)
            if tr:
                await message.reply_text(f"⏩ Seeked to <code>{seconds}s</code>.")
            else:
                await message.reply_text("⚠️ Cannot seek on this stream.")

    @app.on_message(filters.command(["volume", "vol"]) & filters.group)
    async def cmd_volume(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        req_id, _ = _requester_info(message)
        if not await can_control(client, chat_id, req_id):
            await message.reply_text("🔒 Admin-Only mode is enabled.")
            return
        if len(message.command) < 2 or not message.command[1].isdigit():
            await message.reply_text("💡 Usage: <code>/volume 100</code> (1–200)")
            return
        vol = int(message.command[1])
        if runtime.player:
            clamped = await runtime.player.set_volume(chat_id, vol)
            await runtime.db.update_settings(chat_id, volume=clamped)
            await message.reply_text(f"🔊 Volume set to <b>{clamped}%</b>.")
