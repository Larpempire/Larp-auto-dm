import os
import json
import random
import asyncio
import threading
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import discord
from discord import app_commands

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"
LOG_FILE = "stealth.log"

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": ["http://46.47.197.210:3128", "http://79.174.12.190:80"],
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 60, "message": "Test message"},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

config = load_config()

class StealthSelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.running = False
        self.status = "stopped"

    async def start(self, token: str):
        self.token = token
        self.running = True
        self.status = "online"
        self.session = aiohttp.ClientSession()
        logger.info("[+] SelfBot STARTED - HTTP MODE")
        asyncio.create_task(self._autopost_loop())

    async def send_message(self, channel_id: str, content: str):
        proxy = random.choice(config.get("proxies", [None]))
        logger.info(f"[SEND ATTEMPT] To {channel_id} via {proxy}")

        try:
            async with self.session.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": self.token, "Content-Type": "application/json"},
                json={"content": content + "‎" * random.randint(0, 6)},
                proxy=proxy
            ) as r:
                if r.status in (200, 201):
                    logger.info("[+] MESSAGE SENT SUCCESSFULLY")
                else:
                    text = await r.text()
                    logger.error(f"[-] FAILED {r.status} - {text[:200]}")
        except Exception as e:
            logger.error(f"Send exception: {e}")

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                await self.send_message(cfg["channel_id"], cfg["message"])
            await asyncio.sleep(30)  # test every 30s

selfbot = StealthSelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logger.info(f"[+] Management bot online as {bot.user}")
    await tree.sync()
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

@tree.command(name="setup-token", description="Connect token")
async def setup_token(interaction: discord.Interaction, token: str):
    await interaction.response.defer(ephemeral=True)
    config["user_token"] = token
    save_config(config)
    await selfbot.start(token)
    await interaction.followup.send("Token set.", ephemeral=True)

@tree.command(name="autopost", description="Toggle autopost")
async def autopost_cmd(interaction: discord.Interaction, enabled: bool, channel_id: str):
    config["autopost"]["enabled"] = enabled
    config["autopost"]["channel_id"] = channel_id
    save_config(config)
    await interaction.response.send_message(f"Autopost: {enabled}", ephemeral=True)

@tree.command(name="status", description="Status")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Status: {selfbot.status}", ephemeral=True)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "alive"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
    else:
        logger.error("No BOT_TOKEN")
