# Clip Bot

## Purpose
A custom-built Python bot that bridges Twitch chat and Discord via webhooks, enabling users to create and share clips easily.

## Local Mandates
- **Surgical Updates**: This is a locally developed service. When modifying `bot.py`, ensure the Docker container is rebuilt with `docker compose build`.
- **Credential Management**: Do not hardcode API keys. Use the `.env` file for `TWITCH_BOT_TOKEN`, `TWITCH_CLIENT_ID`, and `DISCORD_WEBHOOK_URL`.
- **Rate Limiting**: Adhere to the `CLIP_COOLDOWN_SECONDS` to avoid Twitch Helix API rate limits.
- **Token Type**: `TWITCH_BOT_TOKEN` must be a user OAuth token with `clips:edit`, `chat:read`, and `chat:edit` scopes.
