# Discord Music Bot

A modern Discord music bot built on **discord.py 2.5+** and **yt-dlp**.
Plays tracks from YouTube and any other site supported by yt-dlp, with a
clean slash-command interface and interactive button controls.

[Русская версия →](README_RU.md)

---

## Features

- **Slash commands** for everything
- **Vote-skip** with a configurable threshold
- **Loop modes**: off / track / queue
- **Queue shuffle**
- **Volume control** (0–200%)
- **Auto-disconnect** on empty queue or empty voice channel
- **Search picker** when the query isn't a direct URL
- **Inline playback controls** on the now-playing message

---

## Commands

| Command | Description |
|---|---|
| `/play <query>` | Play a track or add it to the queue (URL or search query) |
| `/skip` | Vote-skip the current track (admins / requester skip instantly) |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/stop` | Stop playback and leave the voice channel |
| `/queue` | Show the queue |
| `/nowplaying` | Show the current track with a progress bar |
| `/clear` | Clear the queue |
| `/remove <position>` | Remove a track from the queue |
| `/shuffle` | Shuffle the queue |
| `/loop [mode]` | Cycle the loop mode or set it explicitly |
| `/volume <0-200>` | Set the playback volume |
| `/help` | List all available commands |
| `/about` | About the bot and the author |

---

## Installation

### Requirements

- **Python 3.13+**
- **uv** — install from [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/)
- **FFmpeg** available on your `PATH` (install via `apt`, `brew`, `choco`, or download from [ffmpeg.org](https://ffmpeg.org))
- A Discord application and bot token — create one at the [Discord Developer Portal](https://discord.com/developers/applications)

### Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/Dellenoam/DiscordMusicBot.git
   cd DiscordMusicBot
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Create a `.env` file (see `.env.example`):
   ```env
   DISCORD_TOKEN=your_token_here
   ```

4. Run the bot:
   ```bash
   uv run musicbot
   ```

---

## Docker

The repository ships a `Dockerfile` and `compose.yaml` with FFmpeg pre-installed.

1. Copy and fill in the env file:
   ```bash
   cp .env.example .env
   # edit .env and set DISCORD_TOKEN
   ```

2. Start the container:
   ```bash
   docker compose up -d
   ```

---

## Configuration via `.env`

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | **Required.** Your bot token. |
| `SKIP_VOTE_RATIO` | `0.5` | Fraction of listeners required to vote-skip (0.0–1.0). |
| `ADMIN_INSTANT_SKIP` | `true` | Allow admins to skip instantly. |
| `REQUESTER_INSTANT_SKIP` | `true` | Allow the requester to skip their own track instantly. |
| `INACTIVITY_TIMEOUT` | `180` | Seconds of inactivity (empty queue) before leaving voice. |
| `EMPTY_CHANNEL_GRACE` | `30` | Seconds to wait after the voice channel empties before disconnecting. `0` = disconnect immediately. |
| `ACTIVITY_NAME` | *(empty)* | Bot "Playing …" status text. Empty means no activity. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `YDL_FORCE_IPV4` | `true` | Force yt-dlp to use IPv4 (avoids YouTube IPv6 throttling on some hosts). |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

<p align="center">Made with ❤️ by <a href="https://github.com/Dellenoam">Dellenoam</a></p>
