import os
import json
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import discord
from discord import app_commands
from discord.ui import Modal, TextInput

CONFIG_FILE = "config.json"
API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [],
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Mesaj automat."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "cooldown_seconds": 86400},
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

# ====================== SELF-BOT (user token) ======================
class SelfBot:
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

    async def stop(self):
        self.running = False
        if self._autopost_task:
            self._autopost_task.cancel()
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.status = "stopped"

    async def rest_send(self, channel_id, content):
        url = f"{API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        async with self.session.post(url, headers=headers, json={"content": content}) as r:
            if r.status not in (200, 201):
                print(f"[selfbot] REST fail {r.status}")

    async def _run(self):
        while self.running:
            try:
                await self._connect()
            except Exception as e:
                print(f"[selfbot] Error: {e}")
            await asyncio.sleep(5)

    async def _connect(self):
        async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json") as ws:
            self.ws = ws
            hb = None
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT: continue
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
            if hb: hb.cancel()

    def _identify(self):
        return {"op": 2, "d": {
            "token": self.token,
            "capabilities": 8189,
            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
            "compress": False
        }}

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval)
            try: await ws.send_json({"op": 1, "d": self.seq})
            except: return

    async def _dispatch(self, data):
        t, d = data.get("t"), data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            print(f"[selfbot] Logat ca {self.user.get('username')}")
            self._autopost_task = asyncio.create_task(self._autopost_loop())
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _on_message(self, d):
        if d.get("guild_id"): return
        author = d.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"): return
        cfg = config["autodm"]
        if not cfg.get("enabled"): return
        aid = str(author.get("id"))
        now = int(time.time())
        cd = int(cfg.get("cooldown_seconds", 86400))
        if now < config["cooldowns"].get(aid, 0) + cd: return
        config["cooldowns"][aid] = now
        save_config(config)
        await self.rest_send(d["channel_id"], cfg["message"])

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.rest_send(cfg["channel_id"], cfg["message"])
                except: pass
                await asyncio.sleep(max(5, int(cfg.get("interval_seconds", 3600))))
            else:
                await asyncio.sleep(10)

selfbot = SelfBot()

# ====================== BOT OFICIAL (slash commands) ======================
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    print(f"[bot] Logat ca {bot.user}")
    gid = os.getenv("GUILD_ID")
    if gid:
        guild = discord.Object(id=int(gid))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

# Comenzi exact ca în varianta veche
class TokenModal(Modal, title="Configureaza user token"):
    token = TextInput(label="User token", placeholder="Lipeste tokenul contului tau")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        user = await selfbot.validate(tok)
        if not user:
            await interaction.followup.send("Token invalid.", ephemeral=True)
            return
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send(f"Self-bot conectat ca {user.get('username')}", ephemeral=True)

@tree.command(name="setup-token", description="Adauga tokenul contului tau (self-bot)")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())

class AutoMsgModal(Modal, title="Mesaj automat pe canal"):
    channel_id = TextInput(label="ID canal")
    interval = TextInput(label="Interval (secunde)", default="3600")
    message = TextInput(label="Mesaj", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            iv = int(str(self.interval.value).strip())
        except:
            await interaction.response.send_message("Interval invalid.", ephemeral=True)
            return
        config["autopost"] = {"enabled": True, "channel_id": str(self.channel_id.value).strip(),
                              "interval_seconds": iv, "message": str(self.message.value)}
        save_config(config)
        await interaction.response.send_message(f"Autopost activat pe canal {self.channel_id.value}", ephemeral=True)

@tree.command(name="startautomsg", description="Configureaza mesajul automat pe un canal")
async def startautomsg(interaction: discord.Interaction):
    await interaction.response.send_modal(AutoMsgModal())

class AutoDMModal(Modal, title="Raspuns automat la DM"):
    message = TextInput(label="Mesaj raspuns", style=discord.TextStyle.paragraph)
    cooldown = TextInput(label="Cooldown (secunde)", default="86400")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cd = int(str(self.cooldown.value).strip())
        except:
            await interaction.response.send_message("Cooldown invalid.", ephemeral=True)
            return
        config["autodm"] = {"enabled": True, "message": str(self.message.value), "cooldown_seconds": cd}
        save_config(config)
        await interaction.response.send_message("Auto-DM configurat.", ephemeral=True)

@tree.command(name="autodm", description="Configureaza raspunsul automat la DM")
async def autodm(interaction: discord.Interaction):
    await interaction.response.send_modal(AutoDMModal())

@tree.command(name="status", description="Vezi starea self-bot-ului")
async def status_cmd(interaction: discord.Interaction):
    ap = config["autopost"]
    dm = config["autodm"]
    txt = (f"**Self-bot:** {selfbot.status} {selfbot.user.get('username') if selfbot.user else ''}\n"
           f"**Auto-post:** {'ON' if ap['enabled'] else 'OFF'} | {ap['interval_seconds']}s\n"
           f"**Auto-DM:** {'ON' if dm['enabled'] else 'OFF'} | cooldown {dm['cooldown_seconds']}s")
    await interaction.response.send_message(txt, ephemeral=True)

@tree.command(name="stop", description="Opreste self-bot-ul")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    config["autopost"]["enabled"] = False
    save_config(config)
    await interaction.response.send_message("Self-bot oprit.", ephemeral=True)

# Health server
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"bot": "online", "selfbot": selfbot.status}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

def start_web():
    port = int(os.getenv("PORT", 8080))
    ThreadingHTTPServer(("0.0.0.0", port), Health).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
    else:
        print("Lipseste BOT_TOKEN in environment!")
