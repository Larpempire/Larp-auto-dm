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
from fake_useragent import UserAgent

CONFIG_FILE = "config.json"
API = "https://discord.com/api/v10"

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("stealth.log", encoding="utf-8"), logging.StreamHandler()])
logger = logging.getLogger(__name__)

ua = UserAgent()

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [
        "http://45.79.1.23:3128",
        "http://167.172.248.53:3128",
        "http://139.59.128.40:3128",
        "socks5://167.172.248.53:1080",
        "http://165.22.50.226:3128",
        "http://159.65.241.82:3128",
        "http://138.68.161.60:3128",
        "socks5://159.65.241.82:1080"
    ],
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 300, "messages": ["Hey, just checking in.", "What's up everyone?", "Test message here."]},
    "autodm": {"enabled": True, "message": "Hey! Sorry, I'm a bit busy right now.", "cooldown_seconds": 120},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        if k not in data:
            data[k] = v
        elif isinstance(v, dict):
            for sk, sv in v.items():
                data[k].setdefault(sk, sv)
    return data

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()

class UltimateSelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.running = False
        self.status = "stopped"

    async def start(self, token):
        self.token = token
        self.running = True
        self.status = "online"
        self.session = aiohttp.ClientSession()
        logger.info("[ULTIMATE] Max Stealth Mode Activated")
        asyncio.create_task(self._autopost_loop())

    async def send_message(self, channel_id, base_content):
        proxy = random.choice(config.get("proxies", [None]))
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": ua.random,
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCJ9"
        }

        content = base_content + "‎" * random.randint(0, 12) + random.choice(["", "🙂", "🔥", "👀", "👍"])

        await asyncio.sleep(random.uniform(2.0, 6.5))

        try:
            async with self.session.post(
                f"{API}/channels/{channel_id}/typing",
                headers={"Authorization": self.token},
                proxy=proxy
            ):
                await asyncio.sleep(random.uniform(2.5, 7.5))
        except:
            pass

        await asyncio.sleep(random.uniform(1.8, 5.8))

        try:
            async with self.session.post(
                f"{API}/channels/{channel_id}/messages",
                headers=headers,
                json={"content": content},
                proxy=proxy
            ) as r:
                if r.status in (200, 201):
                    logger.info(f"[+] SUCCESS Sent to {channel_id}")
                else:
                    logger.warning(f"[-] Failed {r.status}")
        except Exception as e:
            logger.error(f"Send error: {e}")

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                msg = random.choice(cfg.get("messages", [cfg.get("message", "Test")]))
                await self.send_message(cfg["channel_id"], msg)
            await asyncio.sleep(cfg.get("interval_seconds", 300) + random.uniform(-40, 60))

selfbot = UltimateSelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logger.info(f"[+] Management bot online as {bot.user}")
    await tree.sync()
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

class TokenModal(discord.ui.Modal, title="Setup Token"):
    token = discord.ui.TextInput(label="User Token")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send("✅ Started.", ephemeral=True)

@tree.command(name="setup-token", description="Set token")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())

@tree.command(name="autopost", description="Set autopost")
async def autopost_cmd(interaction: discord.Interaction, enabled: bool, channel_id: str, interval: int, message: str):
    config["autopost"] = {"enabled": enabled, "channel_id": channel_id, "interval_seconds": interval, "messages": [message]}
    save_config(config)
    await interaction.response.send_message("Autopost set.", ephemeral=True)

@tree.command(name="status", description="Status")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Status: {selfbot.status}", ephemeral=True)

@tree.command(name="stop", description="Stop")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    await interaction.response.send_message("Stopped.", ephemeral=True)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "alive"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

def start_health():
    port = int(os.getenv("PORT", 8080))
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health, daemon=True).start()
    bot.run(os.getenv("BOT_TOKEN"))
