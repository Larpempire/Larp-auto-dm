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
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        ]

    def get_proxy(self):
        if not config["proxies"]:
            return None
        proxy = config["proxies"][self.proxy_index % len(config["proxies"])]
        self.proxy_index += 1
        return proxy

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

    async def _run(self):
        while self.running:
            try:
                proxy = self.get_proxy()
                ua = random.choice(self.user_agents)
                async with self.session.ws_connect("wss://gateway.discord.gg/?v=10&encoding=json", proxy=proxy) as ws:
                    self.ws = ws
                    await self._identify()
                    await self._gateway_loop()
            except Exception as e:
                print(f"[Gateway] {e}")
                await asyncio.sleep(random.uniform(3, 8))

    def _identify(self):
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 8189,
                "properties": {"os": "Windows", "browser": "Chrome", "device": "desktop"},
                "presence": {"status": random.choice(["online", "idle"]), "since": int(time.time()*1000), "activities": [], "afk": False}
            }
        }

    async def _gateway_loop(self):
        while self.running:
            msg = await self.ws.recv()
            data = json.loads(msg)
            if data.get("s") is not None:
                self.seq = data["s"]
            op = data.get("op")
            if op == 10:
                interval = data["d"]["heartbeat_interval"] / 1000
                asyncio.create_task(self._heartbeat(interval))
            elif op == 0:
                await self._dispatch(data)

    async def _heartbeat(self, interval):
        while self.running:
            await asyncio.sleep(interval + random.uniform(-2, 2))
            try:
                await self.ws.send_json({"op": 1, "d": self.seq})
            except:
                return

    async def _dispatch(self, data):
        t, d = data.get("t"), data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            asyncio.create_task(self._autopost_loop())
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def send_message(self, channel_id: str, content: str):
        proxy = self.get_proxy()
        ua = random.choice(self.user_agents)
        if time.time() - self.last_action < 5:
            await asyncio.sleep(random.uniform(5, 12))

        if random.random() < 0.7:
            try:
                async with self.session.post(f"{API}/channels/{channel_id}/typing", headers={"Authorization": self.token}, proxy=proxy): pass
            except: pass
            await asyncio.sleep(random.uniform(1.5, 4.5))

        content = content + ("\u200b" * random.randint(0, 4))
        headers = {"Authorization": self.token, "Content-Type": "application/json", "User-Agent": ua}
        async with self.session.post(f"{API}/channels/{channel_id}/messages", headers=headers, json={"content": content}, proxy=proxy) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", 12))
                await asyncio.sleep(retry + random.uniform(4, 12))
            elif r.status in (200, 201):
                self.last_action = time.time()

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.send_message(cfg["channel_id"], cfg["message"])
                except: pass
            await asyncio.sleep(cfg.get("base_interval", 60) + random.uniform(-12, 22))

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

selfbot = SelfBot()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    print(f"[BOT] Online ca {bot.user}")
    gid = os.getenv("GUILD_ID")
    if gid:
        guild = discord.Object(id=int(gid))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    if config.get("user_token"):
        await selfbot.start(config["user_token"])

class TokenModal(Modal, title="Setup User Token"):
    token = TextInput(label="User Token", placeholder="mfa.xxxxx")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        selfbot.token = tok
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send("Token setat și self-bot pornit.", ephemeral=True)

@tree.command(name="setup-token", description="Set user token")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())

@tree.command(name="startautomsg", description="Setup autopost")
async def startautomsg(interaction: discord.Interaction):
    # Poți extinde cu modal dacă vrei, dar pentru rapiditate
    await interaction.response.send_message("Editează config.json pentru autopost.", ephemeral=True)

@tree.command(name="autodm", description="Toggle AutoDM")
async def autodm(interaction: discord.Interaction):
    config["autodm"]["enabled"] = not config["autodm"]["enabled"]
    save_config(config)
    await interaction.response.send_message(f"AutoDM: {'ON' if config['autodm']['enabled'] else 'OFF'}", ephemeral=True)

@tree.command(name="status", description="Status")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message(f"SelfBot: {selfbot.status}", ephemeral=True)

@tree.command(name="stop", description="Stop selfbot")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    await interaction.response.send_message("Stopped.", ephemeral=True)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

def start_web():
    ThreadingHTTPServer(("0.0.0.0", 8080), Health).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if bot_token:
        bot.run(bot_token)
