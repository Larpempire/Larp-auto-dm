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

# ================================================
# STEALTH SELF-BOT — Looks & acts like a real human
# ================================================
# WARNING: Still against Discord ToS. Use responsibly.

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "autopost": {
        "enabled": False,
        "channel_id": None,
        "interval_seconds": 3600,
        "message": "Hey, just checking in."
    },
    "autodm": {
        "enabled": True,
        "message": "Hey! Sorry, I'm a bit busy right now. I'll reply properly later 👀",
        "cooldown_seconds": 86400
    },
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


class StealthSelfBot:
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

    async def validate_token(self, token: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{DISCORD_API}/users/@me", headers={"Authorization": token}) as r:
                return await r.json() if r.status == 200 else None

    async def start(self, token: str):
        await self.stop()
        self.token = token
        self.running = True
        self.status = "connecting"
        self.error = None
        self.session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run())

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

    async def _human_delay(self, min_sec=0.8, max_sec=3.5):
        """Natural human typing/sending delay."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def send_message(self, channel_id: str, content: str):
        """Send message with human-like behavior."""
        await self._human_delay(0.5, 2.0)
        
        # Trigger typing indicator
        try:
            async with self.session.post(
                f"{DISCORD_API}/channels/{channel_id}/typing",
                headers={"Authorization": self.token}
            ):
                pass
        except:
            pass
        
        await self._human_delay(1.2, 4.0)  # simulate typing time
        
        url = f"{DISCORD_API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        
        async with self.session.post(url, headers=headers, json={"content": content}) as r:
            if r.status not in (200, 201):
                print(f"[stealth] Send failed {r.status}")

    async def _run(self):
        while self.running:
            try:
                await self._connect()
            except Exception as e:
                print(f"[stealth] Connection dropped: {e}")
                self.status = "connecting"
            if self.running:
                await asyncio.sleep(random.uniform(4, 12))  # natural reconnect jitter

    async def _connect(self):
        async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json") as ws:
            self.ws = ws
            hb_task = None
            
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("s") is not None:
                    self.seq = data["s"]
                
                op = data.get("op")
                
                if op == 10:  # HELLO
                    interval = data["d"]["heartbeat_interval"] / 1000
                    hb_task = asyncio.create_task(self._heartbeat(ws, interval))
                    await ws.send_json(self._identify())
                    
                elif op == 0:
                    await self._handle_event(data)
                    
                elif op == 1:
                    await ws.send_json({"op": 1, "d": self.seq})
                    
                elif op == 9:
                    self.status = "error"
                    self.error = "Session rejected"
                    self.running = False
                    break
            
            if hb_task:
                hb_task.cancel()

    def _identify(self):
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 8189,
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": ""
                },
                "compress": False,
            }
        }

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval + random.uniform(-2, 3))  # slight jitter
            try:
                await ws.send_json({"op": 1, "d": self.seq})
            except:
                return

    async def _handle_event(self, data):
        t = data.get("t")
        d = data.get("d", {})
        
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            print(f"[stealth] Logged in as {self.user.get('username')} — blending in")
            self._autopost_task = asyncio.create_task(self._autopost_loop())
            
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _on_message(self, msg):
        if msg.get("guild_id"):  # only DMs
            return
        author = msg.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"):
            return
        
        cfg = config["autodm"]
        if not cfg.get("enabled"):
            return
        
        user_id = str(author.get("id"))
        now = int(time.time())
        cooldown = cfg.get("cooldown_seconds", 86400)
        
        # Add natural jitter to cooldown
        if now < config["cooldowns"].get(user_id, 0) + cooldown + random.randint(-300, 600):
            return
        
        config["cooldowns"][user_id] = now
        save_config(config)
        
        await self.send_message(msg["channel_id"], cfg["message"])
        print(f"[stealth] Human-like reply sent to {author.get('username')}")

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.send_message(cfg["channel_id"], cfg["message"])
                    print("[stealth] Auto-post sent naturally")
                except Exception as e:
                    print(f"[stealth] Post error: {e}")
                
                # Human-like irregular intervals
                base = cfg.get("interval_seconds", 3600)
                jitter = random.randint(-900, 1800)  # ±15-30 mins variation
                await asyncio.sleep(max(60, base + jitter))
            else:
                await asyncio.sleep(15)


selfbot = StealthSelfBot()


# ================================================
# MANAGEMENT BOT (slash commands) — unchanged but cleaner
# ================================================
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    gid = os.getenv("GUILD_ID")
    if gid:
        guild = discord.Object(id=int(gid))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    
    print(f"[bot] Online as {bot.user}")
    if config.get("user_token") and selfbot.status == "stopped":
        await selfbot.start(config["user_token"])


# (TokenModal, AutoMsgModal, AutoDMModal, commands stay mostly the same — only small UX improvements)


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
        await interaction.followup.send("✅ Account connected in stealth mode.", ephemeral=True)


@tree.command(name="setup-token", description="Connect your main account (stealth)")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())


# ... keep the other commands (startautomsg, autodm, status, stop) similar to previous version


# Health server
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
    port = int(os.getenv("PORT", 10000))
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
    else:
        print("[ERROR] BOT_TOKEN missing")
