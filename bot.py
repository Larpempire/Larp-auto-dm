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
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 60, "messages": ["Hey, just checking in.", "What's up?", "Test message."]},
    "autodm": {"enabled": True, "message": "Hey! Sorry, I'm a bit busy right now.", "cooldown_seconds": 60},
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

class SelfBot:
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

    async def validate(self, token):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{API}/users/@me", headers={"Authorization": token}) as r:
                return await r.json() if r.status == 200 else None

    async def start(self, token):
        await self.stop()
        self.token = token
        self.running = True
        self.status = "connecting"
        self.session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run())
        # Pornește autopost imediat (fără să aștepte gateway READY)
        self._autopost_task = asyncio.create_task(self._autopost_loop())
        logger.info("[+] SelfBot started - autopost loop active")

    async def stop(self):
        self.running = False
        if self._autopost_task:
            self._autopost_task.cancel()
            self._autopost_task = None
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.status = "stopped"
        self.user = None

    async def send_message(self, channel_id, base_content):
        proxy = random.choice(config.get("proxies", [None]))
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": ua.random,
            "X-Super-Properties": "eyJvc3MiOiJXaW5kb3dzIiwgImJyb3dzZXIiOiJDaHJvbWUiLCAiZGV2aWNlIjoiZGVza3RvcCJ9"
        }

        content = base_content + "‎" * random.randint(0, 10) + random.choice(["", "🙂", "🔥", "👀"])

        try:
            async with self.session.post(
                f"{API}/channels/{channel_id}/typing",
                headers={"Authorization": self.token},
                proxy=proxy
            ):
                await asyncio.sleep(random.uniform(2.0, 6.5))
        except:
            pass

        await asyncio.sleep(random.uniform(1.5, 5.0))

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

    async def _run(self):
        while self.running:
            try:
                await self._connect()
            except Exception as e:
                logger.error(f"Connection lost: {e}")
            if self.running:
                await asyncio.sleep(5)

    async def _connect(self):
        async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json") as ws:
            self.ws = ws
            hb = None
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("s") is not None:
                    self.seq = data["s"]
                op = data.get("op")
                if op == 10:
                    interval = data["d"]["heartbeat_interval"] / 1000
                    hb = asyncio.create_task(self._heartbeat(ws, interval))
                    await ws.send_json(self._identify())
                elif op == 0:
                    await self._dispatch(data)
                elif op == 1:
                    await ws.send_json({"op": 1, "d": self.seq})
                elif op == 9:
                    self.status = "error"
                    self.running = False
                    break
            if hb:
                hb.cancel()

    def _identify(self):
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 8189,
                "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
                "compress": False,
            }
        }

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval + random.uniform(-1, 2))
            try:
                await ws.send_json({"op": 1, "d": self.seq})
            except:
                return

    async def _dispatch(self, data):
        t = data.get("t")
        d = data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            logger.info(f"[+] Logged in as {self.user.get('username')}")
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _on_message(self, d):
        if d.get("guild_id"):
            return
        author = d.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"):
            return
        cfg = config["autodm"]
        if not cfg.get("enabled"):
            return
        aid = str(author.get("id"))
        now = int(time.time())
        cd = int(cfg.get("cooldown_seconds", 60))
        if now < config["cooldowns"].get(aid, 0) + cd:
            return
        config["cooldowns"][aid] = now
        save_config(config)
        await self.send_message(d["channel_id"], cfg["message"])

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                msg = random.choice(cfg.get("messages", [cfg.get("message", "Test")]))
                await self.send_message(cfg["channel_id"], msg)
            await asyncio.sleep(max(10, int(cfg.get("interval_seconds", 60))))

selfbot = SelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logger.info(f"[+] Management bot online as {bot.user}")
    try:
        await tree.sync()
        logger.info("[+] Commands synced")
    except Exception as e:
        logger.error(f"Sync error: {e}")

    if config.get("user_token") and selfbot.status == "stopped":
        await selfbot.start(config["user_token"])

class TokenModal(discord.ui.Modal, title="Setup User Token"):
    token = discord.ui.TextInput(label="User Token")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        user = await selfbot.validate(tok)
        if not user:
            await interaction.followup.send("Invalid token.", ephemeral=True)
            return
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send("✅ Token set and started.", ephemeral=True)

@tree.command(name="setup-token", description="Set user token")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())

@tree.command(name="autopost", description="Set autopost")
async def autopost_cmd(interaction: discord.Interaction, enabled: bool, channel_id: str, interval: int, message: str):
    config["autopost"] = {"enabled": enabled, "channel_id": channel_id, "interval_seconds": interval, "messages": [message]}
    save_config(config)
    await interaction.response.send_message(f"Autopost set: {enabled}", ephemeral=True)

@tree.command(name="autodm", description="Set autodm")
async def autodm_cmd(interaction: discord.Interaction, enabled: bool, message: str, cooldown: int):
    config["autodm"] = {"enabled": enabled, "message": message, "cooldown_seconds": cooldown}
    save_config(config)
    await interaction.response.send_message("Autodm set.", ephemeral=True)

@tree.command(name="status", description="Check status")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Selfbot: {selfbot.status}", ephemeral=True)

@tree.command(name="stop", description="Stop selfbot")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    await interaction.response.send_message("Selfbot stopped.", ephemeral=True)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "alive", "selfbot": selfbot.status}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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
