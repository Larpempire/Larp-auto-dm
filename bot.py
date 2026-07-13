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

bot = commands.Bot(command_prefix="!", intents=None)

class UltimateStealthBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=None)
        self.http_session = None

    async def setup_hook(self):
        self.http_session = AsyncSession(impersonate="chrome126")
        print("[+] ULTIMATE STEALTH READY")

    async def on_ready(self):
        print(f"[+] ONLINE -> {self.user}")

    async def send_message(self, channel_id, content, user_token=None):
        if not user_token and config.get("user_tokens"):
            user_token = list(config["user_tokens"].values())[0]
        if not user_token:
            return False

        await asyncio.sleep(random.uniform(1.5, 6.5))

        headers = {
            "Authorization": user_token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCJ9",
            "Referer": "https://discord.com/channels/@me"
        }

        if random.random() < 0.75:
            try:
                async with self.http_session.post(f"https://discord.com/api/v10/channels/{channel_id}/typing", headers={"Authorization": user_token}): pass
            except: pass
            await asyncio.sleep(random.uniform(2.5, 7))

        content = content + "‎" * random.randint(0, 9)

        for attempt in range(4):
            try:
                async with self.http_session.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=headers,
                    json={"content": content}
                ) as r:
                    if r.status in (200, 201):
                        print("[+] SEND SUCCESS")
                        return True
                    elif r.status == 429:
                        await asyncio.sleep(int(r.headers.get("Retry-After", 10)) + random.uniform(10, 30))
            except Exception as e:
                print(f"[-] Attempt {attempt}: {e}")
            await asyncio.sleep(random.uniform(5, 15))
        return False

bot.run(os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN"))
