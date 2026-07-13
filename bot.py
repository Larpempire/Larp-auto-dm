import os
import json
import time
import random
import asyncio
import threading
import aiohttp
import discord
from discord import app_commands
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG_FILE = "config.json"
API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [],
    "autopost": {"enabled": False, "channel_id": None, "base_interval": 60, "message": "Mesaj automat."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "base_cooldown": 20},
    "cooldowns": {}
}

def load_config(): ... # (la fel ca înainte)
def save_config(cfg): ... # (la fel)

config = load_config()

class SelfBot:
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
        self.user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"]

    def get_proxy(self):
        if not config["proxies"]: return None
        p = config["proxies"][self.proxy_index % len(config["proxies"])]
        self.proxy_index += 1
        return p

    async def start(self, token):
        await self.stop()
        self.token = token
        self.running = True
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self._run())

    async def _run(self):
        while self.running:
            try:
                proxy = self.get_proxy()
                headers = {"User-Agent": random.choice(self.user_agents)}
                async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json", proxy=proxy, headers=headers) as ws:
                    self.ws = ws
                    await self._identify()
                    await self._gateway_loop()
            except:
                await asyncio.sleep(random.uniform(3, 8))

    def _identify(self):
        return {"op": 2, "d": {
            "token": self.token,
            "capabilities": 8189,
            "properties": {"os": "Windows", "browser": "Chrome", "device": "desktop"},
            "presence": {"status": random.choice(["online", "idle"]), "since": int(time.time()*1000), "activities": [], "afk": False}
        }}

    async def _gateway_loop(self): ... # (la fel ca înainte, cu _on_message)

    async def send_message(self, channel_id, content):
        # Extra stealth
        proxy = self.get_proxy()
        ua = random.choice(self.user_agents)
        await asyncio.sleep(random.uniform(0.8, 3.5))  # human delay

        # Typing variabil
        if random.random() < 0.75:
            try:
                async with self.session.post(f"{API}/channels/{channel_id}/typing", headers={"Authorization": self.token}, proxy=proxy): pass
            except: pass
            await asyncio.sleep(random.uniform(2, 5))

        # Zero-width + variation
        content = content + "‎" * random.randint(0, 3)  # invisible char

        async with self.session.post(f"{API}/channels/{channel_id}/messages",
                                     headers={"Authorization": self.token, "Content-Type": "application/json", "User-Agent": ua},
                                     json={"content": content}, proxy=proxy) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", 15))
                await asyncio.sleep(retry + random.uniform(5, 15))
            elif r.status in (200, 201):
                self.last_action = time.time()

    # AutoDM + Autopost cu randomizare puternică
    async def _autopost_loop(self):
        while self.running:
            if config["autopost"].get("enabled"):
                try:
                    await self.send_message(config["autopost"]["channel_id"], config["autopost"]["message"])
                except: pass
            await asyncio.sleep(config["autopost"].get("base_interval", 60) + random.uniform(-15, 25))

    async def _on_message(self, d):
        # ... logica AutoDM cu cooldown randomizat între 18-35s
        # (adaug random.uniform pe cooldown)

# (restul codului cu slash commands /setup-token etc. rămâne la fel ca ultima versiune)

if __name__ == "__main__":
    # ... health server + bot.run(BOT_TOKEN)
