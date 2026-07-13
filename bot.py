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

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [],  # list of "http://ip:port" or "http://user:pass@ip:port"
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 60, "messages": ["Mesaj automat."]},
    "autodm": {"enabled": True, "messages": ["Salut! Momentan nu sunt disponibil."], "cooldown_seconds": 20},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in data:
            data[key] = default_value
        elif isinstance(default_value, dict):
            for subkey, subvalue in default_value.items():
                data[key].setdefault(subkey, subvalue)
    return data

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()

class AdvancedStealthBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.ws = None
        self.user = None
        self.seq = None
        self.running = False
        self.status = "stopped"
        self.error = None
        self._task = None
        self._autopost_task = None
        self._status_task = None
        self.proxy_index = 0
        self.last_message_time = 0

    def get_proxy(self):
        if not config["proxies"]:
            return None
        proxy = config["proxies"][self.proxy_index % len(config["proxies"])]
        self.proxy_index += 1
        return proxy

    async def start(self, token: str):
        await self.stop()
        self.token = token
        self.running = True
        self.status = "connecting"
        self.session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run())

    # ... (restul metodelor rămân, dar send_message folosește proxy)

    async def send_message(self, channel_id: str, content: str):
        proxy = self.get_proxy()
        if time.time() - self.last_message_time < 8:
            await asyncio.sleep(8)
        
        if random.random() < 0.5:  # typing mai rar
            try:
                async with self.session.post(f"{DISCORD_API}/channels/{channel_id}/typing", headers={"Authorization": self.token}, proxy=proxy): pass
            except: pass
            await asyncio.sleep(random.uniform(1.5, 3.5))
        
        url = f"{DISCORD_API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        
        async with self.session.post(url, headers=headers, json={"content": content}, proxy=proxy) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", 15))
                await asyncio.sleep(retry + random.randint(3, 8))
            elif r.status in (200, 201):
                self.last_message_time = time.time()

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    msg = random.choice(cfg.get("messages", ["Mesaj automat."]))
                    await self.send_message(cfg["channel_id"], msg)
                except: pass
                await asyncio.sleep(60 + random.randint(-8, 15))
            else:
                await asyncio.sleep(30)

    # AutoDM cu cooldown 15-25s
    async def _on_message(self, msg):
        if msg.get("guild_id"): return
        author = msg.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"): return
        cfg = config["autodm"]
        if not cfg.get("enabled"): return
        user_id = str(author.get("id"))
        now = int(time.time())
        cooldown = cfg.get("cooldown_seconds", 20)
        if now < config["cooldowns"].get(user_id, 0) + cooldown: return
        config["cooldowns"][user_id] = now
        save_config(config)
        reply = random.choice(cfg.get("messages", ["Salut!"]))
        await self.send_message(msg["channel_id"], reply)

# Management bot + health server (la fel ca înainte)

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
