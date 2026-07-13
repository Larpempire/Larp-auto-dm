import discord
from discord.ext import commands, tasks
import random
import json
import os
import time
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from curl_cffi.requests import AsyncSession

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_tokens": {},
        "autopost": {"enabled": False, "channel_id": None, "base_interval": 300, "message": "Mesaj auto."},
        "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "base_cooldown": 60},
        "cooldowns": {}
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

class UltimateStealthBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.http_session = None
        self.presence_task = None

    async def setup_hook(self):
        self.http_session = AsyncSession(impersonate="chrome126")
        # Headers ultimate
        self.http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCIsICJyZWZlcnJlciI6IiIsICJyZWZlcnJpbmdfZG9tYWluIjoiIn0=",  # UPDATE cu al tău din browser DevTools
            "X-Discord-Locale": "en-US",
            "Referer": "https://discord.com/channels/@me",
            "Origin": "https://discord.com"
        })
        print("[+] ULTIMATE STEALTH SESSION READY (chrome126)")

    async def on_ready(self):
        await bot.tree.sync()
        print(f"[+] ULTIMATE BOT ONLINE -> {self.user}")
        if not self.presence_task:
            self.presence_task = asyncio.create_task(self.random_presence_loop())

    async def random_presence_loop(self):
        while True:
            try:
                status = random.choice(["online", "idle"])
                activity = random.choice([None, discord.Game("Playing something"), discord.Streaming(name="Streaming", url="https://twitch.tv")])
                await self.change_presence(status=status, activity=activity)
            except: pass
            await asyncio.sleep(random.uniform(180, 600))  # random presence change

    # ULTIMATE send_message cu toate bypass-urile
    async def send_message(self, channel_id, content, user_token=None):
        if not user_token and config.get("user_tokens"):
            user_token = list(config["user_tokens"].values())[0]
        if not user_token:
            return False

        # Heavy human jitter
        await asyncio.sleep(random.uniform(1.5, 6.5))

        headers = {
            "Authorization": user_token,
            "Content-Type": "application/json",
            "User-Agent": self.http_session.headers["User-Agent"],
            "X-Super-Properties": self.http_session.headers.get("X-Super-Properties", ""),
            "Referer": "https://discord.com/channels/@me",
            "Origin": "https://discord.com"
        }

        # Typing indicator variabil
        if random.random() < 0.8:
            try:
                async with self.http_session.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/typing",
                    headers={"Authorization": user_token}
                ): pass
            except: pass
            await asyncio.sleep(random.uniform(2.5, 7.5))

        # Zero-width + variație
        content = content + "‎" * random.randint(0, 9)

        for attempt in range(4):
            try:
                async with self.http_session.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=headers,
                    json={"content": content}
                ) as r:
                    if r.status in (200, 201):
                        print("[+] ULTIMATE SEND SUCCESS")
                        return True
                    elif r.status == 429:
                        retry = int(r.headers.get("Retry-After", 15))
                        await asyncio.sleep(retry + random.uniform(10, 30))
                    else:
                        print(f"[-] Send failed {r.status}")
            except Exception as e:
                print(f"[-] Attempt {attempt} error: {e}")
            await asyncio.sleep(random.uniform(5, 15))
        return False

# Slash commands (la fel ca înainte + ping)
@bot.tree.command(name="add_user_token", description="Adauga user token")
async def add_user_token(interaction: discord.Interaction, name: str, token: str):
    config.setdefault("user_tokens", {})[name] = token
    save_config(config)
    await interaction.response.send_message(f"Token '{name}' adăugat!", ephemeral=True)

@bot.tree.command(name="autopost", description="Configure autopost")
async def autopost_cmd(interaction: discord.Interaction, enabled: bool, channel_id: str, interval: int, message: str):
    config["autopost"] = {"enabled": enabled, "channel_id": channel_id, "base_interval": interval, "message": message}
    save_config(config)
    await interaction.response.send_message("Autopost set!", ephemeral=True)

@bot.tree.command(name="autodm", description="Configure autodm")
async def autodm_cmd(interaction: discord.Interaction, enabled: bool, message: str, cooldown: int):
    config["autodm"] = {"enabled": enabled, "message": message, "base_cooldown": cooldown}
    save_config(config)
    await interaction.response.send_message("Autodm set!", ephemeral=True)

@bot.tree.command(name="ping", description="Test ultimate stealth")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("ULTIMATE STEALTH MODE ACTIVE", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
