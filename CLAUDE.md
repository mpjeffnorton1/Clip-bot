# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run locally:**
```bash
pip install -r requirements.txt
python bot.py
```

**Docker (primary deployment):**
```bash
docker-compose down && docker-compose up -d --build   # Apply code changes (--build required)
docker-compose down && docker-compose up -d           # Restart with new .env only
docker-compose logs clip-bot                          # Tail logs
```

`docker-compose restart` does NOT reload `.env` — always use `down && up` when changing config.
`--build` is required whenever `bot.py` changes, otherwise Docker uses a cached image.

## Architecture

Single-file Python bot (`bot.py`) that bridges Twitch chat and Discord via webhooks.

**Data flow:**
1. `ClipBot` (extends `twitchio.commands.Bot`) listens on a Twitch channel for `!clip`
2. Checks role-based access (`CLIP_ALLOWED_ROLES`) and 30s cooldown
3. Uses the app-access token (fetched via client credentials, cached) to resolve the broadcaster ID
4. Uses the user OAuth token (`TWITCH_BOT_TOKEN` minus `oauth:` prefix) to create the clip via Helix API — requires `clips:edit` scope
5. Polls until the clip is processed (thumbnail_url present — up to 8 retries × 3s)
6. Posts a rich embed to a Discord webhook (Twitch purple `#9147FF`, includes title, duration, thumbnail)

**Key methods in `bot.py`:**
- `get_app_token()` — app-access token cache/refresh (used for user lookup only)
- `_user_token()` — strips `oauth:` prefix from `TWITCH_BOT_TOKEN` for API use
- `create_clip()` — resolves broadcaster ID with app token, creates clip with user token
- `wait_for_clip()` — polling loop for clip readiness
- `send_to_discord()` — Discord webhook embed
- `clip_command()` — top-level `!clip` handler (auth + cooldown + orchestration)

## Configuration

All config is via environment variables (see `.env.example`). Key variables:

| Variable | Purpose |
|---|---|
| `TWITCH_BOT_TOKEN` | User OAuth token (`oauth:...`) — must have `clips:edit chat:read chat:edit` scopes |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Helix API credentials (from dev.twitch.tv) |
| `TWITCH_CHANNEL` / `BROADCASTER_LOGIN` | Channel to monitor / clip target (both lowercase) |
| `DISCORD_WEBHOOK_URL` | Discord posting endpoint |
| `CLIP_ALLOWED_ROLES` | `broadcaster`, `moderator`, or `everyone` (comma-separated) |
| `CLIP_COOLDOWN_SECONDS` | Channel-wide cooldown (default `30`) |

In Docker, all variables are passed explicitly in `docker-compose.yml`.

## Token generation

`TWITCH_BOT_TOKEN` must be a user OAuth token issued by **your own Twitch app** (matching `TWITCH_CLIENT_ID`) with `clips:edit+chat:read+chat:edit` scopes. Tokens from twitchapps.com/tmi will not work for clip creation as they are tied to a different Client ID.

Generate via the implicit grant flow (log in as the bot account):
```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost&response_type=token&scope=clips:edit+chat:read+chat:edit
```
Copy the `access_token` from the redirect URL and set `TWITCH_BOT_TOKEN=oauth:<token>`.
