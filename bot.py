import os
import json
import time
import random
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import discord
from discord import app_commands
from curl_cffi.requests import AsyncSession  # ULTIMATE BYPASS

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "bot_token": None,
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Hey, just checking in."},
    "autodm": {"enabled": True, "message": "Hey! Sorry, I'm busy. Reply later 👀", "cooldown_seconds": 86400},
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
    return data

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()

class StealthSelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.ws = None
        self.running = False
        self.status = "stopped"

    async def start(self, token):
        await self.stop()
        self.token = token
        self.running = True
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self._run())

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def send_message(self, channel_id, content):
        await asyncio.sleep(random.uniform(0.8, 3.5))

        # Typing
        if random.random() < 0.75:
            try:
                async with self.session.post(f"{DISCORD_API}/channels/{channel_id}/typing", headers={"Authorization": self.token}): pass
            except: pass
            await asyncio.sleep(random.uniform(2, 5.5))

        content = content + "‎" * random.randint(0, 6)

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCJ9",
        }

        async with self.session.post(f"{DISCORD_API}/channels/{channel_id}/messages", headers=headers, json={"content": content}) as r:
            if r.status in (200, 201):
                print("[+] Message sent stealth")
            elif r.status == 429:
                await asyncio.sleep(int(r.headers.get("Retry-After", 15)) + random.uniform(5, 15))

    async def _run(self):
        while self.running:
            try:
                async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json") as ws:
                    self.ws = ws
                    await ws.send_json(self._identify())
                    await self._gateway_loop(ws)
            except:
                await asyncio.sleep(random.uniform(5, 15))

    def _identify(self):
        return {"op": 2, "d": {
            "token": self.token,
            "capabilities": 8189,
            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
            "presence": {"status": "online", "afk": False}
        }}

    async def _gateway_loop(self, ws):
        while self.running:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("t") == "MESSAGE_CREATE":
                    await self._on_message(data["d"])

    async def _on_message(self, msg):
        # AutoDM logic (la fel ca vechiul cod)
        # ... (păstrează logica ta veche)
        pass

selfbot = StealthSelfBot()

# Bot management (slash)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f"[BOT] Online {client.user}")
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

# Slash commands (adaugă-le pe ale tale)

# Health server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

if __name__ == "__main__":
    threading.Thread(target=lambda: ThreadingHTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), HealthHandler).serve_forever(), daemon=True).start()
    client.run(os.getenv("BOT_TOKEN"))
