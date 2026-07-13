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
# ADVANCED STEALTH SELF-BOT
# ================================================

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Mesaj automat."},
    "autodm": {
        "enabled": True,
        "messages": ["Salut! Momentan nu sunt disponibil."],
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
        for task in [self._autopost_task, self._status_task]:
            if task: task.cancel()
        if self.ws and not self.ws.closed: await self.ws.close()
        if self.session and not self.session.closed: await self.session.close()
        self.status = "stopped"
        self.user = None

    async def _human_delay(self, min_sec=0.8, max_sec=4.0):
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def set_random_status(self):
        try:
            statuses = ["online", "idle", "dnd"]
            await self.session.patch(
                f"{DISCORD_API}/users/@me/settings",
                headers={"Authorization": self.token, "Content-Type": "application/json"},
                json={"status": random.choice(statuses), "custom_status": {"text": random.choice(["Busy rn", "Chilling", ""])}}
            )
        except: pass

    async def send_message(self, channel_id: str, content: str):
        await self._human_delay(0.6, 2.8)
        try:
            async with self.session.post(f"{DISCORD_API}/channels/{channel_id}/typing", headers={"Authorization": self.token}): pass
        except: pass
        await self._human_delay(1.5, 5.0)
        
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
                print(f"[stealth] Connection lost: {e}")
                self.status = "connecting"
            if self.running:
                await asyncio.sleep(random.uniform(5, 15))

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
                    self.running = False
                    break
            if hb_task: hb_task.cancel()

    def _identify(self):
        return {"op": 2, "d": {
            "token": self.token,
            "capabilities": 8189,
            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
            "compress": False,
        }}

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval + random.uniform(-3, 3))
            try: await ws.send_json({"op": 1, "d": self.seq})
            except: return

    async def _handle_event(self, data):
        t = data.get("t")
        d = data.get("d", {})
        if t == "READY":
            self.user = d.get("user", {})
            self.status = "online"
            print(f"[stealth] Logged in as {self.user.get('username')}")
            self._autopost_task = asyncio.create_task(self._autopost_loop())
            self._status_task = asyncio.create_task(self._status_cycler())
        elif t == "MESSAGE_CREATE":
            await self._on_message(d)

    async def _status_cycler(self):
        while self.running:
            await self.set_random_status()
            await asyncio.sleep(random.randint(1800, 5400))

    async def _on_message(self, msg):
        if msg.get("guild_id"): return
        author = msg.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"): return
        cfg = config["autodm"]
        if not cfg.get("enabled"): return
        user_id = str(author.get("id"))
        now = int(time.time())
        cooldown = cfg.get("cooldown_seconds", 86400)
        if now < config["cooldowns"].get(user_id, 0) + cooldown + random.randint(-600, 900): return
        config["cooldowns"][user_id] = now
        save_config(config)
        reply = random.choice(cfg.get("messages", ["Salut!"]))
        await self.send_message(msg["channel_id"], reply)
        print(f"[stealth] Replied to {author.get('username')}")

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.send_message(cfg["channel_id"], cfg["message"])
                except Exception as e:
                    print(f"[stealth] Autopost error: {e}")
                base = cfg.get("interval_seconds", 3600)
                jitter = random.randint(-1200, 2400)
                await asyncio.sleep(max(300, base + jitter))
            else:
                await asyncio.sleep(20)


selfbot = AdvancedStealthBot()


# ================================================
# MANAGEMENT BOT (slash commands)
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
    print(f"[bot] Logged in as {bot.user}")
    if config.get("user_token") and selfbot.status == "stopped":
        await selfbot.start(config["user_token"])


class TokenModal(discord.ui.Modal, title="Setup Token"):
    token = discord.ui.TextInput(label="User token", placeholder="Lipeste tokenul")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tok = str(self.token.value).strip()
        user = await selfbot.validate_token(tok)
        if not user:
            await interaction.followup.send("Token invalid.", ephemeral=True)
            return
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        await interaction.followup.send("✅ Self-bot pornit in stealth mode.", ephemeral=True)


@tree.command(name="setup-token", description="Adauga user token")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())


class AutoPostModal(discord.ui.Modal, title="Auto Send in Channel"):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="123456789012345678")
    interval = discord.ui.TextInput(label="Interval secunde", default="3600")
    message = discord.ui.TextInput(label="Mesaj", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            iv = int(str(self.interval.value).strip())
        except:
            await interaction.response.send_message("Intervalul trebuie sa fie numar.", ephemeral=True)
            return
        config["autopost"] = {
            "enabled": True,
            "channel_id": str(self.channel_id.value).strip(),
            "interval_seconds": iv,
            "message": str(self.message.value)
        }
        save_config(config)
        await interaction.response.send_message(f"✅ Auto-send setat pe canal {config['autopost']['channel_id']} la fiecare {iv} secunde.", ephemeral=True)


@tree.command(name="startautomsg", description="Configureaza auto send in channel")
async def startautomsg(interaction: discord.Interaction):
    if not config.get("user_token"):
        await interaction.response.send_message("Mai intai /setup-token", ephemeral=True)
        return
    await interaction.response.send_modal(AutoPostModal())


class AutoDMModal(discord.ui.Modal, title="Auto DM Messages"):
    messages = discord.ui.TextInput(
        label="Mesaje (unul pe linie)",
        style=discord.TextStyle.paragraph,
        placeholder="Salut!\nHey, ce mai faci?\nSunt ocupat, vorbim mai tarziu."
    )
    cooldown = discord.ui.TextInput(label="Cooldown secunde", default="86400")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cd = int(str(self.cooldown.value).strip())
        except:
            await interaction.response.send_message("Cooldown-ul trebuie sa fie numar.", ephemeral=True)
            return
        msg_list = [line.strip() for line in str(self.messages.value).strip().split("\n") if line.strip()]
        if not msg_list:
            msg_list = ["Salut! Momentan nu sunt disponibil."]
        config["autodm"] = {"enabled": True, "messages": msg_list, "cooldown_seconds": cd}
        save_config(config)
        await interaction.response.send_message(f"✅ Auto-DM setat cu {len(msg_list)} mesaje diferite.", ephemeral=True)


@tree.command(name="autodm", description="Configureaza mesaje auto DM")
async def autodm(interaction: discord.Interaction):
    if not config.get("user_token"):
        await interaction.response.send_message("Mai intai /setup-token", ephemeral=True)
        return
    await interaction.response.send_modal(AutoDMModal())


@tree.command(name="status", description="Vezi status")
async def status_cmd(interaction: discord.Interaction):
    ap = config["autopost"]
    dm = config["autodm"]
    txt = (f"**Self-bot:** {selfbot.status}\n"
           f"**Auto-post:** {'on' if ap['enabled'] else 'off'} | canal: {ap['channel_id']} | {ap['interval_seconds']}s\n"
           f"**Auto-DM:** {'on' if dm['enabled'] else 'off'} | {len(dm['messages'])} mesaje | cooldown {dm['cooldown_seconds']}s")
    await interaction.response.send_message(txt, ephemeral=True)


@tree.command(name="stop", description="Opreste self-bot")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    config["autopost"]["enabled"] = False
    save_config(config)
    await interaction.response.send_message("Self-bot oprit.", ephemeral=True)


# ================================================
# HEALTH SERVER
# ================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"bot": "online", "selfbot": selfbot.status}).encode()
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
        print("[ERROR] BOT_TOKEN lipseste")
