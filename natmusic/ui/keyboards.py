"""Refined inline keyboard builders for Nat Music."""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from natmusic.core.player import EQ_PRESETS
from natmusic.core.queue import ChatQueueState
from natmusic.database import ChatSettings


def now_playing_keyboard(state: ChatQueueState) -> InlineKeyboardMarkup:
    pause_label = "▶" if state.is_paused else "⏸"
    queue_count = len(state.upcoming)
    loop_label = f"🔁 {state.loop_mode.label}"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏮", callback_data="np:prev"),
                InlineKeyboardButton(pause_label, callback_data="np:toggle"),
                InlineKeyboardButton("⏭", callback_data="np:skip"),
                InlineKeyboardButton("⏹", callback_data="np:stop"),
            ],
            [
                InlineKeyboardButton("🔀 Shuffle", callback_data="np:shuffle"),
                InlineKeyboardButton(loop_label, callback_data="np:loop"),
                InlineKeyboardButton(f"🔊 {state.volume}%", callback_data="np:vol_menu"),
                InlineKeyboardButton(f"📋 Queue ({queue_count})", callback_data="np:queue:1"),
            ],
            [
                InlineKeyboardButton("🎛 EQ", callback_data="np:eq_menu"),
                InlineKeyboardButton("❤️ Save", callback_data="np:save"),
                InlineKeyboardButton("✖ Close", callback_data="np:close"),
            ],
        ]
    )


def volume_keyboard(current_volume: int) -> InlineKeyboardMarkup:
    presets = [50, 80, 100, 130, 160]
    row1 = [
        InlineKeyboardButton(
            f"• {v}% •" if v == current_volume else f"{v}%",
            callback_data=f"np:vol:{v}",
        )
        for v in presets
    ]
    return InlineKeyboardMarkup(
        [
            row1,
            [
                InlineKeyboardButton("🔉 -15%", callback_data="np:vol_step:-15"),
                InlineKeyboardButton("🔊 +15%", callback_data="np:vol_step:15"),
            ],
            [InlineKeyboardButton("« Back to Player", callback_data="np:back")],
        ]
    )


def eq_keyboard(current_eq: str) -> InlineKeyboardMarkup:
    buttons = []
    row: list[InlineKeyboardButton] = []
    for key, info in EQ_PRESETS.items():
        prefix = "✅ " if key == current_eq else ""
        row.append(
            InlineKeyboardButton(
                f"{prefix}{info['label']}",
                callback_data=f"eq:set:{key}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("« Back to Player", callback_data="np:back")])
    return InlineKeyboardMarkup(buttons)


def queue_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav_row: list[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("‹ Prev", callback_data=f"q:page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{max(1, total_pages)}", callback_data="q:noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ›", callback_data=f"q:page:{page + 1}"))

    return InlineKeyboardMarkup(
        [
            nav_row,
            [
                InlineKeyboardButton("🔀 Shuffle", callback_data="np:shuffle"),
                InlineKeyboardButton("🗑 Clear", callback_data="q:clear"),
                InlineKeyboardButton("« Player", callback_data="np:back"),
            ],
        ]
    )


def settings_keyboard(settings: ChatSettings) -> InlineKeyboardMarkup:
    admin_txt = "🔒 Admin-Only: ON" if settings.admin_only else "🔓 Admin-Only: OFF"
    vote_txt = f"🗳 Vote-Skip: {'ON' if settings.vote_skip else 'OFF'} ({settings.vote_threshold})"
    leave_txt = f"🚪 Auto-Leave: {'ON' if settings.auto_leave else 'OFF'}"
    qual_txt = f"🎧 Quality: {settings.quality.title()}"
    eq_txt = f"🎛 EQ: {settings.eq_preset.title()}"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(admin_txt, callback_data="set:toggle:admin_only")],
            [InlineKeyboardButton(vote_txt, callback_data="set:toggle:vote_skip")],
            [
                InlineKeyboardButton(qual_txt, callback_data="set:cycle:quality"),
                InlineKeyboardButton(eq_txt, callback_data="np:eq_menu"),
            ],
            [InlineKeyboardButton(leave_txt, callback_data="set:toggle:auto_leave")],
            [InlineKeyboardButton("✖ Close", callback_data="np:close")],
        ]
    )


def help_keyboard(active_tab: str = "playback") -> InlineKeyboardMarkup:
    tabs = [
        ("playback", "🎵 Playback"),
        ("queue", "📋 Queue & Lists"),
        ("radio", "📻 Radio & EQ"),
        ("admin", "⚙️ Admin"),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label in tabs:
        text = f"• {label} •" if key == active_tab else label
        row.append(InlineKeyboardButton(text, callback_data=f"help:tab:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✖ Close", callback_data="np:close")])
    return InlineKeyboardMarkup(rows)


def start_keyboard(
    bot_username: str,
    support_chat: str = "",
    updates_channel: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "➕ Add Nat Music to Group",
                url=f"https://t.me/{bot_username}?startgroup=true",
            )
        ],
        [
            InlineKeyboardButton("📖 Commands & Help", callback_data="help:tab:playback"),
            InlineKeyboardButton("📻 Live Radio", callback_data="help:tab:radio"),
        ],
    ]
    links: list[InlineKeyboardButton] = []
    if support_chat.startswith("http"):
        links.append(InlineKeyboardButton("💬 Support", url=support_chat))
    if updates_channel.startswith("http"):
        links.append(InlineKeyboardButton("📢 Updates", url=updates_channel))
    if links:
        rows.append(links)
    return InlineKeyboardMarkup(rows)
