# Twitch Clip Bot

A custom Python bot that listens for `!clip` in Twitch chat and posts the resulting clip to a Discord webhook.

## Configuration

- **Image**: Built locally via `Dockerfile`.
- **Language**: Python (TwitchIO)
- **Environment**: `.env` (Twitch/Discord credentials, cooldowns, roles).
- **Primary Command**: `!clip`

## Usage

```bash
docker compose up -d --build
```

## Management

- Rebuild is required whenever `bot.py` or dependencies change.
- `docker compose restart` will NOT reload the `.env` file. Use `down && up` for config changes.
- **Allowed Roles**: Configurable via `CLIP_ALLOWED_ROLES` (broadcaster, moderator, everyone).
