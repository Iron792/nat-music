"""Glassmorphic Now-Playing card generator & clean text formatters for Nat Music."""

from __future__ import annotations

import html
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from natmusic.core.extractor import format_duration
from natmusic.core.queue import ChatQueueState, Track

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_CANDIDATES if bold else _FONT_CANDIDATES[1:] + _FONT_CANDIDATES[:1]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), size], radius=radius, fill=255)
    return mask


async def _fetch_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    return None


def render_now_playing_card_sync(
    track: Track,
    art_img: Image.Image | None = None,
    bot_name: str = "Nat Music",
    eq_preset: str = "flat",
    volume: int = 100,
) -> io.BytesIO:
    """Render a 1280x720 dark glassmorphic Now-Playing card into a PNG BytesIO buffer."""
    W, H = 1280, 720

    if art_img is not None:
        bg = art_img.resize((W, H), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=34))
        overlay = Image.new("RGBA", (W, H), (10, 12, 20, 175))
        canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
    else:
        canvas = Image.new("RGBA", (W, H), (14, 17, 28, 255))
        draw_bg = ImageDraw.Draw(canvas)
        draw_bg.ellipse((-120, -140, 620, 600), fill=(99, 102, 241, 70))
        draw_bg.ellipse((740, 220, 1400, 880), fill=(236, 72, 153, 60))

    # Glassmorphic card container
    card_box = (64, 64, W - 64, H - 64)
    card_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_layer)
    card_draw.rounded_rectangle(
        card_box,
        radius=36,
        fill=(20, 24, 38, 195),
        outline=(255, 255, 255, 42),
        width=2,
    )
    canvas = Image.alpha_composite(canvas, card_layer)
    draw = ImageDraw.Draw(canvas)

    # Album art square on left
    art_size = 420
    art_x, art_y = 114, (H - art_size) // 2
    if art_img is not None:
        # Center crop to square
        aw, ah = art_img.size
        side = min(aw, ah)
        cropped = art_img.crop(((aw - side) // 2, (ah - side) // 2, (aw + side) // 2, (ah + side) // 2))
        thumb = cropped.resize((art_size, art_size), Image.Resampling.LANCZOS).convert("RGBA")
    else:
        thumb = Image.new("RGBA", (art_size, art_size), (34, 40, 64, 255))
        tdraw = ImageDraw.Draw(thumb)
        tdraw.ellipse((90, 90, 330, 330), fill=(99, 102, 241, 220))
        tdraw.ellipse((175, 175, 245, 245), fill=(20, 24, 38, 255))

    mask = _rounded_mask((art_size, art_size), radius=28)
    canvas.paste(thumb, (art_x, art_y), mask)

    # Right column typography
    text_x = art_x + art_size + 56
    font_badge = _load_font(22, bold=True)
    font_title = _load_font(44, bold=True)
    font_artist = _load_font(28, bold=False)
    font_meta = _load_font(23, bold=False)

    # Brand & Mode pill
    mode_tag = "VIDEO STREAM" if track.is_video else ("LIVE RADIO" if track.is_live else "AUDIO STREAM")
    pill_text = f"  {bot_name.upper()}  •  {mode_tag}  "
    draw.rounded_rectangle(
        (text_x, 140, text_x + 430, 184),
        radius=22,
        fill=(99, 102, 241, 230),
    )
    draw.text((text_x + 18, 149), pill_text, font=font_badge, fill=(255, 255, 255, 255))

    # Title (up to 2 lines)
    title_clean = track.title.strip()
    line1 = _truncate(title_clean, 24)
    line2 = ""
    if len(title_clean) > 24:
        rest = title_clean[24:].lstrip()
        if rest:
            line2 = _truncate(rest, 24)

    draw.text((text_x, 220), line1, font=font_title, fill=(248, 250, 252, 255))
    if line2:
        draw.text((text_x, 276), line2, font=font_title, fill=(248, 250, 252, 255))

    # Artist
    artist_y = 345 if line2 else 300
    draw.text(
        (text_x, artist_y),
        _truncate(track.artist, 36),
        font=font_artist,
        fill=(148, 163, 184, 255),
    )

    # Progress bar
    bar_x1, bar_y = text_x, 456
    bar_x2 = W - 120
    draw.rounded_rectangle((bar_x1, bar_y, bar_x2, bar_y + 10), radius=5, fill=(71, 85, 105, 180))
    fill_end = bar_x1 + int((bar_x2 - bar_x1) * (0.65 if track.is_live else 0.35))
    draw.rounded_rectangle((bar_x1, bar_y, fill_end, bar_y + 10), radius=5, fill=(129, 140, 248, 255))
    draw.ellipse((fill_end - 9, bar_y - 4, fill_end + 9, bar_y + 14), fill=(255, 255, 255, 255))

    # Duration & Meta row
    draw.text((bar_x1, bar_y + 24), "0:00", font=font_meta, fill=(148, 163, 184, 255))
    dur_label = "LIVE" if track.is_live else track.duration_str
    draw.text((bar_x2 - 80, bar_y + 24), dur_label, font=font_meta, fill=(226, 232, 240, 255))

    footer_text = f"Requested by {_truncate(track.requester_name, 20)}   •   Vol {volume}%   •   EQ: {eq_preset.title()}"
    draw.text((text_x, 548), footer_text, font=font_meta, fill=(203, 213, 225, 255))

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    buf.name = "nat_music_card.png"
    return buf


async def build_now_playing_card(
    track: Track,
    bot_name: str = "Nat Music",
    eq_preset: str = "flat",
    volume: int = 100,
) -> io.BytesIO:
    art = await _fetch_image(track.thumbnail)
    return render_now_playing_card_sync(
        track, art_img=art, bot_name=bot_name, eq_preset=eq_preset, volume=volume
    )


def format_progress_bar(state: ChatQueueState, width: int = 14) -> str:
    track = state.current
    if not track:
        return ""
    if track.is_live or track.duration_sec <= 0:
        return "🔴 ━━━━━━━━━━━━━━ LIVE"
    elapsed = state.seek_offset
    if not state.is_paused and state.started_at > 0:
        elapsed += int(time.monotonic() - state.started_at)
    elapsed = max(0, min(elapsed, track.duration_sec))
    ratio = elapsed / track.duration_sec
    pos = min(width - 1, int(ratio * width))
    bar = "━" * pos + "●" + "─" * (width - pos - 1)
    return f"{format_duration(elapsed)} {bar} {track.duration_str}"


def format_now_playing_caption(state: ChatQueueState, bot_name: str = "Nat Music") -> str:
    track = state.current
    if not track:
        return f"🎵 <b>{html.escape(bot_name)}</b> — Nothing is currently playing."

    status_icon = "⏸ Paused" if state.is_paused else "▶️ Now Playing"
    mode_badge = "🎬 Video" if track.is_video else ("📻 Radio" if track.is_live else "🎧 Audio")
    title = html.escape(_truncate(track.title, 65))
    artist = html.escape(_truncate(track.artist, 45))
    requester = html.escape(_truncate(track.requester_name, 30))

    title_line = (
        f'<a href="{html.escape(track.webpage_url)}">{title}</a>'
        if track.webpage_url.startswith("http")
        else title
    )
    bar = format_progress_bar(state)

    return (
        f"<b>{status_icon}</b>  •  <code>{mode_badge}</code>\n\n"
        f"🎵 <b>{title_line}</b>\n"
        f"👤 {artist}\n"
        f"<code>{bar}</code>\n\n"
        f"🙋 <b>Requested by:</b> {requester}\n"
        f"🔊 <b>Vol:</b> {state.volume}%  |  🔁 <b>Loop:</b> {state.loop_mode.label}  |  🎛 <b>EQ:</b> {state.eq_preset.title()}"
    )
