import os
import json
import time
import random
import asyncio
import threading
import aiohttp
import discord
from discord import app_commands
from discord.ui import Modal, TextInput
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from curl_cffi.requests import AsyncSession  # ULTIMATE BYPASS

CONFIG_FILE = "config.json"
API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [],
    "autopost": {"enabled": False, "channel_id": None, "base_interval": 60, "message": "Mesaj automat."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "base_cooldown": 20},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
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

class StealthSelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.ws = None
        self.user = None
        self.seq = None
        self.running = False
        self.status = "stopped"
        self.proxy_index = 0
        self.last_action = 0
        self.user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"]

    def get_proxy(self):
        if not config["proxies"]:
            return None
        p = config["proxies"][self.proxy_index % len(config["proxies"])]
        self.proxy_index += 1
        return p

    async def start(self, token):
        await self.stop()
        self.token = token
        self.running = True
        self.status = "connecting"
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self._run())

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        self.status = "stopped"

    async def send_message(self, channel_id: str, content: str):
        await asyncio.sleep(random.uniform(0.8, 3.5))

        # Typing
        if random.random() < 0.75:
            try:
                async with self.session.post(f"{API}/channels/{channel_id}/typing", headers={"Authorization": self.token}): pass
            except: pass
            await asyncio.sleep(random.uniform(2, 5.5))

        content = content + "‎" * random.randint(0, 6)

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": random.choice(self.user_agents),
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCJ9"
        }

        async with self.session.post(f"{API}/channels/{channel_id}/messages", headers=headers, json={"content": content}) as r:
            if r.status in (200, 201):
                self.last_action = time.time()
            elif r.status == 429:
                await asyncio.sleep(int(r.headers.get("Retry-After", 15)) + random.uniform(5, 15))

    async def _run(self):
        while self.running:
            try:
                proxy = self.get_proxy()
                async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json", proxy=proxy) as ws:
                    self.ws = ws
                    await ws.send_json(self._identify())
                    await self._gateway_loop(ws)
            except:
                await asyncio.sleep(random.uniform(4, 12))

    def _identify(self):
        return {"op": 2, "d": {
            "token": self.token,
            "capabilities": 8189,
            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
            "presence": {"status": random.choice(["online", "idle"]), "afk": False}
        }}

    async def _gateway_loop(self, ws):
        while self.running:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("s") is not None:
                    self.seq = data["s"]
                if data.get("op") == 0:
                    await self._handle_event(data)

    async def _handle_event(self, data):
        t = data.get("t")
        d = data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            asyncio.create_task(self._autopost_loop())
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.send_message(cfg["channel_id"], cfg["message"])
                except: pass
            await asyncio.sleep(cfg.get("base_interval", 60) + random.uniform(-15, 25))

    async def _on_message(self, d):
        if d.get("guild_id"): return
        author = d.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"): return
        cfg = config["autodm"]
        if not cfg.get("enabled"): return
        aid = str(author.get("id"))
        now = int(time.time())
        cd = cfg.get("base_cooldown", 20)
        if now < config["cooldowns"].get(aid, 0) + cd - random.randint(0, 5): return
        config["cooldowns"][aid] = now
        save_config(config)
        await self.send_message(d["channel_id"], cfg["message"])

selfbot = StealthSelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    print(f"[BOT] Online ca {bot.user}")
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

# Slash commands (păstrează-le pe ale tale)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

if __name__ == "__main__":
    threading.Thread(target=lambda: ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", 8080))), HealthHandler).serve_forever(), daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN")
    if bot_token:
        bot.run(bot_token)
