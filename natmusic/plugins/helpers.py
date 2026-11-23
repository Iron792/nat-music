"""Shared permission checks, assistant auto-join, and Now-Playing dispatcher."""

from __future__ import annotations

import html
import logging

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import UserAlreadyParticipant, UserNotParticipant
from pyrogram.types import Message

from natmusic.config import config
from natmusic.core.clients import runtime
from natmusic.core.queue import ChatQueueState, Track
from natmusic.ui.cards import build_now_playing_card, format_now_playing_caption
from natmusic.ui.keyboards import now_playing_keyboard

logger = logging.getLogger("natmusic.helpers")

HELP_TEXTS: dict[str, str] = {
    "playback": (
        "🎵 <b>Playback Commands</b>\n\n"
        "• <code>/play [song/url]</code> — Stream audio in VC (or reply to audio)\n"
        "• <code>/vplay [query/url]</code> — Stream video in VC\n"
        "• <code>/pplay [song/url]</code> — Insert track at the front of the queue\n"
        "• <code>/pause</code> | <code>/resume</code> — Pause or resume playback\n"
        "• <code>/skip</code> | <code>/prev</code> — Skip or go back to previous track\n"
        "• <code>/seek [seconds]</code> — Jump to a timestamp\n"
        "• <code>/volume [1-200]</code> — Adjust VC stream volume\n"
        "• <code>/stop</code> — Stop playback and clear queue"
    ),
    "queue": (
        "📋 <b>Queue & Saved Playlists</b>\n\n"
        "• <code>/queue</code> — Interactive paginated queue browser\n"
        "• <code>/shuffle</code> — Shuffle upcoming tracks\n"
        "• <code>/loop [off|track|queue]</code> — Cycle or set repeat mode\n"
        "• <code>/remove [pos]</code> — Remove a track by queue number\n"
        "• <code>/move [from] [to]</code> — Reorder a queued track\n"
        "• <code>/clear</code> — Clear upcoming tracks\n"
        "• <code>/playlist</code> — View, play, or manage saved favorites"
    ),
    "radio": (
        "📻 <b>Live Radio & Equalizer</b>\n\n"
        "• <code>/radio</code> — List curated 24/7 radio stations\n"
        "• <code>/radio [lofi|chillhop|synthwave|jazz|bollywood]</code> — Start live radio\n"
        "• <code>/eq</code> — Open interactive EQ preset selector\n"
        "• <code>/eq [flat|bass|studio|vocal|nightcore]</code> — Apply EQ immediately\n"
        "• <code>/np</code> — Refresh Now-Playing card"
    ),
    "admin": (
        "⚙️ <b>Admin & Group Settings</b>\n\n"
        "• <code>/settings</code> — Toggle Admin-Only, Vote-Skip, Quality & Auto-Leave\n"
        "• <code>/auth</code> (reply) — Grant DJ permissions to a user\n"
        "• <code>/unauth</code> (reply) — Revoke DJ permissions\n"
        "• <code>/ping</code> — Check bot latency\n"
        "• <code>/stats</code> — View active voice chats & uptime"
    ),
}


async def is_admin_or_auth(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in config.owner_ids:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}:
            return True
    except Exception:
        pass
    return await runtime.db.is_auth(chat_id, user_id)


async def can_control(client: Client, chat_id: int, user_id: int) -> bool:
    settings = await runtime.db.get_settings(chat_id)
    if not settings.admin_only:
        return True
    return await is_admin_or_auth(client, chat_id, user_id)


async def ensure_assistant_in_chat(chat_id: int) -> str | None:
    """Ensure the assistant userbot is a member of the target group. Returns error text or None."""
    try:
        me = await runtime.assistant.get_me()
        try:
            await runtime.bot.get_chat_member(chat_id, me.id)
            return None
        except UserNotParticipant:
            pass

        chat = await runtime.bot.get_chat(chat_id)
        if chat.type == ChatType.PRIVATE:
            return "Voice chat playback is only available in groups and channels."

        invite_link = chat.invite_link
        if not invite_link:
            invite_link = await runtime.bot.export_chat_invite_link(chat_id)

        try:
            await runtime.assistant.join_chat(invite_link)
        except UserAlreadyParticipant:
            pass
        return None
    except Exception as exc:
        logger.warning("Assistant join failed in %s: %s", chat_id, exc)
        return (
            "I couldn't add the assistant account to this chat. "
            "Please make sure I have 'Invite Users via Link' permission."
        )


async def send_now_playing(chat_id: int, track: Track | None = None) -> None:
    state: ChatQueueState = runtime.queues.get_state(chat_id)
    if track is not None:
        state.current = track
    if not state.current:
        return

    caption = format_now_playing_caption(state, bot_name=config.bot_name)
    markup = now_playing_keyboard(state)

    # Delete previous Now-Playing message to keep chat clean
    if state.now_playing_msg_id:
        try:
            await runtime.bot.delete_messages(chat_id, state.now_playing_msg_id)
        except Exception:
            pass

    if config.use_thumbnail_cards:
        try:
            card_buf = await build_now_playing_card(
                state.current,
                bot_name=config.bot_name,
                eq_preset=state.eq_preset,
                volume=state.volume,
            )
            sent: Message = await runtime.bot.send_photo(
                chat_id,
                photo=card_buf,
                caption=caption,
                reply_markup=markup,
            )
            state.now_playing_msg_id = sent.id
            return
        except Exception as exc:
            logger.debug("Card render fallback to text for %s: %s", chat_id, exc)

    sent = await runtime.bot.send_message(
        chat_id,
        text=caption,
        reply_markup=markup,
        disable_web_page_preview=True,
    )
    state.now_playing_msg_id = sent.id


def format_queue_page(state: ChatQueueState, page: int = 1, per_page: int = 8) -> tuple[str, int]:
    items = list(state.upcoming)
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    lines = ["📋 <b>Playback Queue</b>\n"]
    if state.current:
        lines.append(
            f"▶️ <b>Now:</b> {html.escape(state.current.title)} "
            f"<code>[{state.current.duration_str}]</code>\n"
        )

    if not items:
        lines.append("<i>No upcoming tracks in queue.</i>")
    else:
        start = (page - 1) * per_page
        end = start + per_page
        for idx, tr in enumerate(items[start:end], start=start + 1):
            lines.append(
                f"<b>{idx}.</b> {html.escape(tr.title[:48])} "
                f"<code>[{tr.duration_str}]</code> — <i>{html.escape(tr.requester_name)}</i>"
            )
        lines.append(f"\n<b>Total queued:</b> {len(items)} track(s)")

    return "\n".join(lines), total_pages
