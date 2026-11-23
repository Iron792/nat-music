# Nat Music — Telegram VC Music Bot

**Nat Music** is a modern, refined Telegram Voice & Video Chat music bot built with Python 3.11+, [Pyrogram / Pyrofork](https://github.com/TelegramPlayGround/pyrofork), and [PyTgCalls v2](https://github.com/pytgcalls/pytgcalls). It draws architectural inspiration from open-source GitHub projects such as [AnonXMusic](https://github.com/AnonymousX1025/AnonXMusic) and [AnnieXMusic](https://github.com/CertifiedCoders/AnnieXMusic), while refining the player UI, equalizer controls, persistence, and usability.

## Key Refinements Over Standard Open-Source Bots

- **Glassmorphic Now-Playing Cards**: Renders 1280×720 dark-mode album artwork cards (`natmusic/ui/cards.py`) with blurred backdrops, progress bars, stream badges (`AUDIO STREAM`, `VIDEO STREAM`, `LIVE RADIO`), and active EQ/volume indicators.
- **Streamlined Inline Control Deck**: Compact 3-row button layout (`⏮ / ⏸ / ⏭ / ⏹`, `🔀 Shuffle`, `🔁 Loop`, `🔊 Vol`, `📋 Queue`, `🎛 EQ`, `❤️ Save`, `✖ Close`) with sub-menus for volume steps and equalizer presets.
- **Zero-Config SQLite Persistence**: Runs out-of-the-box using `aiosqlite` (`natmusic/database.py`) for group settings, authorized DJs, and personal saved playlists—no mandatory external MongoDB cluster required.
- **Live Equalizer Presets**: Built-in FFmpeg audio filters for `Flat`, `Bass Boost`, `Studio Clarity`, `Vocal Boost`, and `Nightcore`.
- **Curated 24/7 Live Radio**: Instant `/radio` presets (`lofi`, `chillhop`, `synthwave`, `jazz`, `bollywood`) plus custom M3U8/stream URLs.
- **Vote-Skip & DJ Auth**: Fair group vote-skipping with configurable thresholds alongside `/auth` & `/unauth` DJ roles.

## Quick Start

### 1. Prerequisites
- Python **3.11+**
- `ffmpeg` installed on your system (`sudo apt install ffmpeg`)
- Telegram `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org)
- `BOT_TOKEN` from [@BotFather](https://t.me/BotFather)
- `STRING_SESSION` (Pyrogram user session for the assistant account that joins voice chats)

### 2. Local Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
bash start.sh
```

### 3. Docker Setup
```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up -d --build
```

## Commands Overview

| Command | Description |
| :--- | :--- |
| `/play [song or url]` | Stream audio in VC (or reply to Telegram audio) |
| `/vplay [query or url]` | Stream video in VC |
| `/pplay [song or url]` | Insert track at the front of the queue |
| `/radio [station]` | Play 24/7 live radio (`lofi`, `chillhop`, `synthwave`, `jazz`, `bollywood`) |
| `/pause`, `/resume`, `/skip`, `/prev`, `/stop` | Playback controls |
| `/seek [seconds]`, `/volume [1-200]` | Seek timestamp or adjust VC volume |
| `/queue`, `/shuffle`, `/loop`, `/remove`, `/move`, `/clear` | Queue management |
| `/playlist [play \| del N]` | Play or manage your saved favorites |
| `/eq`, `/settings`, `/auth`, `/unauth` | Equalizer presets & admin controls |
