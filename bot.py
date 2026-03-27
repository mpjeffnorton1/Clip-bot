import os
import asyncio
import aiohttp
import logging
from twitchio.ext import commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TWITCH_BOT_TOKEN   = os.environ["TWITCH_BOT_TOKEN"]       # oauth:xxxx
TWITCH_CLIENT_ID   = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TWITCH_CHANNEL     = os.environ["TWITCH_CHANNEL"]          # channel to join (no #)
BROADCASTER_LOGIN  = os.environ.get("BROADCASTER_LOGIN", TWITCH_CHANNEL)
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# Optional: restrict !clip to specific roles
CLIP_ALLOWED_ROLES = set(r.strip().lower() for r in os.environ.get("CLIP_ALLOWED_ROLES", "broadcaster,moderator").split(","))
CLIP_COOLDOWN_SECONDS = int(os.environ.get("CLIP_COOLDOWN_SECONDS", "30"))


class ClipBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_BOT_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            nick=os.environ.get("BOT_NICK", "Nightwave_Bot"),
            prefix=os.environ.get("COMMAND_PREFIX", "!"),
            initial_channels=[TWITCH_CHANNEL],
        )
        self._app_token: str | None = None
        self._last_clip_time: float = 0.0

    # ── Twitch app-access token (for API calls, not chat) ──────────────────
    async def get_app_token(self) -> str:
        if self._app_token:
            return self._app_token
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": TWITCH_CLIENT_ID,
                    "client_secret": TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
            )
            data = await r.json()
            self._app_token = data["access_token"]
            log.info("Fetched new app-access token.")
            return self._app_token

    async def get_broadcaster_id(self, session: aiohttp.ClientSession, token: str) -> str | None:
        r = await session.get(
            "https://api.twitch.tv/helix/users",
            params={"login": BROADCASTER_LOGIN},
            headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"},
        )
        data = await r.json()
        users = data.get("data", [])
        return users[0]["id"] if users else None

    def _user_token(self) -> str:
        """Strip the 'oauth:' prefix for use in Authorization headers."""
        return TWITCH_BOT_TOKEN.removeprefix("oauth:")

    # ── Create clip via Helix API ──────────────────────────────────────────
    async def create_clip(self) -> dict | None:
        app_token = await self.get_app_token()
        user_token = self._user_token()
        async with aiohttp.ClientSession() as s:
            # Use app token for user lookup (no special scope needed)
            broadcaster_id = await self.get_broadcaster_id(s, app_token)
            if not broadcaster_id:
                log.error("Could not resolve broadcaster ID for '%s'", BROADCASTER_LOGIN)
                return None

            # Clip creation requires a user token with clips:edit scope
            r = await s.post(
                "https://api.twitch.tv/helix/clips",
                params={"broadcaster_id": broadcaster_id},
                headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {user_token}"},
            )

            if r.status not in (200, 202):
                body = await r.text()
                log.error("Clip creation failed (%s): %s", r.status, body)
                return None

            data = await r.json()
            clips = data.get("data", [])
            return clips[0] if clips else None

    # ── Wait for clip to finish processing, then fetch full metadata ───────
    async def wait_for_clip(self, clip_id: str, retries: int = 8, delay: float = 3.0) -> dict | None:
        token = self._user_token()
        async with aiohttp.ClientSession() as s:
            for attempt in range(retries):
                await asyncio.sleep(delay)
                r = await s.get(
                    "https://api.twitch.tv/helix/clips",
                    params={"id": clip_id},
                    headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"},
                )
                data = await r.json()
                clips = data.get("data", [])
                if clips and clips[0].get("thumbnail_url"):
                    log.info("Clip ready after %d attempt(s).", attempt + 1)
                    return clips[0]
                log.info("Clip not ready yet (attempt %d/%d)...", attempt + 1, retries)
        return None

    # ── Send to Discord ────────────────────────────────────────────────────
    async def send_to_discord(self, clip: dict, requester: str) -> bool:
        clip_url = f"https://clips.twitch.tv/{clip['id']}"
        thumbnail = clip.get("thumbnail_url", "").replace("-preview-480x272.jpg", "-preview-480x272.jpg")
        game = clip.get("game_id", "")  # Helix clips don't return game name, just ID
        duration = round(clip.get("duration", 0), 1)
        title = clip.get("title", "New Clip")

        embed = {
            "title": f"🎬 {title}",
            "url": clip_url,
            "description": f"Clipped by **{requester}** on **{TWITCH_CHANNEL}**",
            "color": 0x9147FF,  # Twitch purple
            "fields": [
                {"name": "⏱ Duration", "value": f"{duration}s", "inline": True},
                {"name": "📺 Channel", "value": TWITCH_CHANNEL, "inline": True},
                {"name": "🔗 Watch", "value": f"[Click here]({clip_url})", "inline": True},
            ],
            "image": {"url": thumbnail} if thumbnail else {},
            "footer": {"text": "Twitch Clip Bot"},
        }

        payload = {
            "content": f"📎 New clip from **{TWITCH_CHANNEL}**! {clip_url}",
            "embeds": [embed],
        }

        async with aiohttp.ClientSession() as s:
            r = await s.post(DISCORD_WEBHOOK_URL, json=payload)
            if r.status in (200, 204):
                log.info("Clip posted to Discord: %s", clip_url)
                return True
            body = await r.text()
            log.error("Discord webhook failed (%s): %s", r.status, body)
            return False

    # ── Bot events ─────────────────────────────────────────────────────────
    async def event_ready(self):
        log.info("ClipBot connected as %s | Channel: #%s", self.nick, TWITCH_CHANNEL)

    async def event_message(self, message):
        if message.echo:
            return
        await self.handle_commands(message)

    # ── Commands ───────────────────────────────────────────────────────────
    @commands.command(name="clip")
    async def clip_command(self, ctx: commands.Context):
        # Role check
        user = ctx.author
        badges = {b.split("/")[0] for b in (user.badges or {}).keys()}
        is_allowed = (
            "broadcaster" in badges
            or "moderator" in badges
            or user.is_mod
            or user.name.lower() == BROADCASTER_LOGIN.lower()
            or not CLIP_ALLOWED_ROLES  # empty = allow everyone
        )

        # If CLIP_ALLOWED_ROLES includes "everyone", open it up
        if "everyone" in CLIP_ALLOWED_ROLES:
            is_allowed = True

        if not is_allowed:
            await ctx.send(f"@{user.name} Only mods and the broadcaster can create clips.")
            return

        # Cooldown check
        import time
        now = time.monotonic()
        remaining = CLIP_COOLDOWN_SECONDS - (now - self._last_clip_time)
        if remaining > 0:
            await ctx.send(f"@{user.name} Clip command is on cooldown ({remaining:.0f}s remaining).")
            return

        self._last_clip_time = now
        await ctx.send(f"@{user.name} Creating clip... ✂️")

        clip_stub = await self.create_clip()
        if not clip_stub:
            await ctx.send("❌ Failed to create clip. Is the stream live?")
            return

        clip_id = clip_stub["id"]
        log.info("Clip created with ID: %s — waiting for processing...", clip_id)
        await ctx.send(f"Clip created! Waiting for it to process... 🎬")

        clip = await self.wait_for_clip(clip_id)
        if not clip:
            # Still post the stub URL even if metadata isn't ready
            clip_url = f"https://clips.twitch.tv/{clip_id}"
            await ctx.send(f"✅ Clip ready (metadata still processing): {clip_url}")
            await self.send_to_discord(
                {"id": clip_id, "title": "New Clip", "duration": 0, "thumbnail_url": ""},
                user.name,
            )
            return

        clip_url = f"https://clips.twitch.tv/{clip['id']}"
        await ctx.send(f"✅ Clip posted to Discord! {clip_url}")
        await self.send_to_discord(clip, user.name)

    @commands.command(name="cliphelp")
    async def cliphelp_command(self, ctx: commands.Context):
        await ctx.send("Commands: !clip — creates a Twitch clip and posts it to Discord. "
                       f"Cooldown: {CLIP_COOLDOWN_SECONDS}s. Allowed: {', '.join(CLIP_ALLOWED_ROLES) or 'everyone'}.")


if __name__ == "__main__":
    bot = ClipBot()
    bot.run()
