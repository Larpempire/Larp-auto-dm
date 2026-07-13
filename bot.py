import os
import json
import time
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [
        "http://46.47.197.210:3128",
        "http://79.174.12.190:80",
        "http://2.56.178.88:808",
        "socks5://195.19.50.180:1080",
        "socks4://37.193.125.68:1090",
        "socks5://37.220.86.195:1080",
        "http://176.99.134.183:8090",
        "http://31.28.4.192:80"
    ],
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 60, "message": "Hey, just checking in."},
    "autodm": {"enabled": True, "message": "Hey! Sorry, I'm a bit busy right now.", "cooldown_seconds": 25},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
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

class StealthSelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.ws = None
        self.user = None
        self.seq = None
        self.running = False
        self.status = "stopped"
        self._task = None
        self._autopost_task = None

    async def validate_token(self, token: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{DISCORD_API}/users/@me", headers={"Authorization": token}) as r:
                return await r.json() if r.status == 200 else None

    async def start(self, token: str):
        await self.stop()
        self.token = token
        self.running = True
        self.status = "connecting"
        self.session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self.running = False
        if self._autopost_task: self._autopost_task.cancel()
        if self.ws and not self.ws.closed: await self.ws.close()
        if self.session and not self.session.closed: await self.session.close()
        self.status = "stopped"

    async def _human_delay(self, min_sec=0.9, max_sec=5.5):
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def send_message(self, channel_id: str, base_content: str):
        proxy = random.choice(config.get("proxies", [None])) if config.get("proxies") else None

        await self._human_delay(0.7, 3.8)

        try:
            async with self.session.post(
                f"{DISCORD_API}/channels/{channel_id}/typing", 
                headers={"Authorization": self.token},
                proxy=proxy
            ):
                await asyncio.sleep(random.uniform(1.8, 6.2))
        except:
            pass

        await self._human_delay(1.1, 4.2)

        noise = "‎" * random.randint(0, 9)
        content = base_content + noise + random.choice(["", " ", "🙂", "🔥", "👀"])

        url = f"{DISCORD_API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}

        try:
            async with self.session.post(url, headers=headers, json={"content": content}, proxy=proxy) as r:
                if r.status in (200, 201):
                    logger.info(f"[+] Sent via {proxy or 'direct'}")
                else:
                    logger.warning(f"[-] Failed {r.status}")
        except Exception as e:
            logger.error(f"Proxy error: {e}")

    async def _run(self):
        while self.running:
            try:
                await self._connect()
            except Exception as e:
                logger.error(f"Connection dropped: {e}")
            if self.running:
                await asyncio.sleep(random.uniform(4, 12))

    async def _connect(self):
        async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json") as ws:
            self.ws = ws
            hb_task = None
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT: continue
                data = json.loads(msg.data)
                if data.get("s") is not None: self.seq = data["s"]
                op = data.get("op")
                if op == 10:
                    interval = data["d"]["heartbeat_interval"] / 1000
                    hb_task = asyncio.create_task(self._heartbeat(ws, interval))
                    await ws.send_json(self._identify())
                elif op == 0:
                    await self._handle_event(data)
                elif op == 1:
                    await ws.send_json({"op": 1, "d": self.seq})
                elif op == 9:
                    break
            if hb_task: hb_task.cancel()

    def _identify(self):
        return {"op": 2, "d": {"token": self.token, "capabilities": 8189, "properties": {"os": "Windows", "browser": "Chrome", "device": ""}, "compress": False}}

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval + random.uniform(-2, 3.5))
            try: await ws.send_json({"op": 1, "d": self.seq})
            except: return

    async def _handle_event(self, data):
        t = data.get("t")
        d = data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            logger.info(f"[+] Logged in as {self.user.get('username')}")
            self._autopost_task = asyncio.create_task(self._autopost_loop())
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _on_message(self, msg):
        if msg.get("guild_id"): return
        author = msg.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"): return
        cfg = config["autodm"]
        if not cfg.get("enabled"): return
        user_id = str(author.get("id"))
        now = int(time.time())
        cooldown = cfg.get("cooldown_seconds", 25)
        if now < config["cooldowns"].get(user_id, 0) + cooldown + random.randint(-8, 12): return
        config["cooldowns"][user_id] = now
        save_config(config)
        await self.send_message(msg["channel_id"], cfg["message"])

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.send_message(cfg["channel_id"], cfg["message"])
                except Exception as e:
                    logger.error(f"Autopost error: {e}")
                await asyncio.sleep(60 + random.uniform(-4, 8))
            else:
                await asyncio.sleep(30)

selfbot = StealthSelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logger.info(f"[+] Management bot online as {bot.user}")
    try:
        synced = await tree.sync()
        logger.info(f"[+] Synced {len(synced)} commands")
    except Exception as e:
        logger.error(f"Sync error: {e}")

    if config.get("user_token") and selfbot.status == "stopped":
        await selfbot.start(config["user_token"])

class TokenModal(discord.ui.Modal, title="Setup Stealth Account"):
    token = discord.ui.TextInput(label="User Token", placeholder="Paste real account token")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        user = await selfbot.validate_token(tok)
        if not user:
            await interaction.followup.send("Invalid token.", ephemeral=True)
            return
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send("✅ Connected.", ephemeral=True)

@tree.command(name="setup-token", description="Connect stealth account")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())

@tree.command(name="autopost", description="Configure autopost")
async def autopost_cmd(interaction: discord.Interaction, enabled: bool, channel_id: str, interval: int, message: str):
    config["autopost"] = {"enabled": enabled, "channel_id": channel_id, "interval_seconds": interval, "message": message}
    save_config(config)
    await interaction.response.send_message(f"Autopost: {'ON' if enabled else 'OFF'} | Interval: {interval}s", ephemeral=True)

@tree.command(name="autodm", description="Configure autodm")
async def autodm_cmd(interaction: discord.Interaction, enabled: bool, message: str, cooldown: int):
    config["autodm"] = {"enabled": enabled, "message": message, "cooldown_seconds": cooldown}
    save_config(config)
    await interaction.response.send_message(f"Autodm: {'ON' if enabled else 'OFF'} | Cooldown: {cooldown}s", ephemeral=True)

@tree.command(name="status", description="Check status")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"**Selfbot Status:** {selfbot.status}", ephemeral=True)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "alive", "selfbot": selfbot.status}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
    else:
        logger.error("[ERROR] BOT_TOKEN missing")
