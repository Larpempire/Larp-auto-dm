import os
import json
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import discord
from discord import app_commands

# NOTA: partea de self-bot (user token) incalca ToS Discord. Risc de ban.

CONFIG_FILE = "config.json"
API = "https://discord.com/api/v10"

DEFAULT_CONFIG = {
    "user_token": None,
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Mesaj automat."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "cooldown_seconds": 86400},
    "cooldowns": {},  # {user_id: last_ts}
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


# ==========================================================================
# SELF-BOT (user token) - conexiune directa la gateway prin aiohttp
# ==========================================================================
class SelfBot:
    def __init__(self):
        self.token = None
        self.session = None
        self.ws = None
        self.user = None          # dict: id, username, avatar
        self.seq = None
        self.running = False
        self.status = "stopped"   # stopped | connecting | online | error
        self.error = None
        self._task = None
        self._autopost_task = None

    async def validate(self, token):
        """Verifica tokenul cu GET /users/@me. Returneaza userul sau None."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{API}/users/@me", headers={"Authorization": token}) as r:
                return await r.json() if r.status == 200 else None

    async def start(self, token):
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
        self.ws = None
        self.session = None
        self.status = "stopped"
        self.user = None

    async def rest_send(self, channel_id, content):
        url = f"{API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        async with self.session.post(url, headers=headers, json={"content": content}) as r:
            if r.status not in (200, 201):
                print(f"[selfbot] REST fail {r.status}: {await r.text()}")

    async def _run(self):
        while self.running:
            try:
                await self._connect()
            except Exception as e:
                print(f"[selfbot] Conexiune pierduta: {e}")
                self.status = "connecting"
            if self.running:
                await asyncio.sleep(5)  # reconnect

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
                if op == 10:  # HELLO
                    interval = data["d"]["heartbeat_interval"] / 1000
                    hb = asyncio.create_task(self._heartbeat(ws, interval))
                    await ws.send_json(self._identify())
                elif op == 0:  # dispatch
                    await self._dispatch(data)
                elif op == 1:  # cere heartbeat
                    await ws.send_json({"op": 1, "d": self.seq})
                elif op == 9:  # sesiune invalida
                    self.status = "error"
                    self.error = "Token invalid / sesiune respinsa"
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
            },
        }

    async def _heartbeat(self, ws, interval):
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send_json({"op": 1, "d": self.seq})
            except Exception:
                return

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
        if d.get("guild_id"):      # doar DM-uri
            return
        author = d.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"):
            return
        cfg = config["autodm"]
        if not cfg.get("enabled"):
            return
        aid = str(author.get("id"))
        now = int(time.time())
        cd = int(cfg.get("cooldown_seconds", 86400))
        if now < config["cooldowns"].get(aid, 0) + cd:
            print(f"[selfbot] Cooldown activ pentru {author.get('username')}")
            return
        config["cooldowns"][aid] = now
        save_config(config)
        await self.rest_send(d["channel_id"], cfg["message"])
        print(f"[selfbot] Raspuns DM catre {author.get('username')} ({aid})")

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    await self.rest_send(cfg["channel_id"], cfg["message"])
                    print("[selfbot] Autopost trimis")
                except Exception as e:
                    print(f"[selfbot] Autopost eroare: {e}")
                await asyncio.sleep(max(5, int(cfg.get("interval_seconds", 3600))))
            else:
                await asyncio.sleep(10)


selfbot = SelfBot()


# ==========================================================================
# BOT OFICIAL (bot token) - comenzi slash /
# ==========================================================================
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    gid = os.getenv("GUILD_ID")
    if gid:  # sync instant pe un server anume (recomandat pentru test)
        guild = discord.Object(id=int(gid))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:    # sync global (poate dura pana la 1h sa apara)
        await tree.sync()
    print(f"[bot] Logat ca {bot.user} - comenzi sincronizate")
    if config.get("user_token") and selfbot.status == "stopped":
        await selfbot.start(config["user_token"])


class TokenModal(discord.ui.Modal, title="Configureaza user token"):
    token = discord.ui.TextInput(label="User token", placeholder="Lipeste tokenul contului tau")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tok = str(self.token.value).strip()
        user = await selfbot.validate(tok)
        if not user:
            await interaction.followup.send("Token invalid.", ephemeral=True)
            return
        config["user_token"] = tok
        save_config(config)
        await selfbot.start(tok)
        uid, ah = user.get("id"), user.get("avatar")
        avatar = f"https://cdn.discordapp.com/avatars/{uid}/{ah}.png?size=256" if ah else None
        embed = discord.Embed(title="Self-bot conectat",
                              description=f"**{user.get('username')}**\nID: {uid}", color=0x23a55a)
        if avatar:
            embed.set_thumbnail(url=avatar)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="setup-token", description="Adauga tokenul contului tau (self-bot)")
async def setup_token(interaction: discord.Interaction):
    await interaction.response.send_modal(TokenModal())


class AutoMsgModal(discord.ui.Modal, title="Mesaj automat pe canal"):
    channel_id = discord.ui.TextInput(label="ID canal", placeholder="123456789012345678")
    interval = discord.ui.TextInput(label="Interval (secunde)", default="3600")
    message = discord.ui.TextInput(label="Mesaj", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            iv = int(str(self.interval.value).strip())
        except ValueError:
            await interaction.response.send_message("Intervalul trebuie sa fie numar.", ephemeral=True)
            return
        config["autopost"] = {"enabled": True, "channel_id": str(self.channel_id.value).strip(),
                              "interval_seconds": iv, "message": str(self.message.value)}
        save_config(config)
        await interaction.response.send_message(
            f"Auto-mesaj setat: canal `{config['autopost']['channel_id']}`, la fiecare `{iv}s`.", ephemeral=True)


@tree.command(name="startautomsg", description="Configureaza mesajul automat pe un canal")
async def startautomsg(interaction: discord.Interaction):
    if not config.get("user_token"):
        await interaction.response.send_message("Mai intai ruleaza /setup-token.", ephemeral=True)
        return
    await interaction.response.send_modal(AutoMsgModal())


class AutoDMModal(discord.ui.Modal, title="Raspuns automat la DM"):
    message = discord.ui.TextInput(label="Mesaj raspuns", style=discord.TextStyle.paragraph)
    cooldown = discord.ui.TextInput(label="Cooldown per persoana (secunde)", default="86400")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cd = int(str(self.cooldown.value).strip())
        except ValueError:
            await interaction.response.send_message("Cooldown-ul trebuie sa fie numar.", ephemeral=True)
            return
        config["autodm"] = {"enabled": True, "message": str(self.message.value), "cooldown_seconds": cd}
        save_config(config)
        await interaction.response.send_message(f"Auto-DM setat, cooldown `{cd}s` per persoana.", ephemeral=True)


@tree.command(name="autodm", description="Configureaza raspunsul automat la DM")
async def autodm(interaction: discord.Interaction):
    if not config.get("user_token"):
        await interaction.response.send_message("Mai intai ruleaza /setup-token.", ephemeral=True)
        return
    await interaction.response.send_modal(AutoDMModal())


@tree.command(name="status", description="Vezi starea self-bot-ului si configurarea")
async def status_cmd(interaction: discord.Interaction):
    ap, dm = config["autopost"], config["autodm"]
    txt = (f"**Self-bot:** {selfbot.status}"
           + (f" ({selfbot.user.get('username')})" if selfbot.user else "")
           + (f"\nEroare: {selfbot.error}" if selfbot.error else "")
           + f"\n\n**Auto-post:** {'on' if ap['enabled'] else 'off'} | canal `{ap['channel_id']}` | {ap['interval_seconds']}s"
           + f"\n**Auto-DM:** {'on' if dm['enabled'] else 'off'} | cooldown {dm['cooldown_seconds']}s")
    await interaction.response.send_message(txt, ephemeral=True)


@tree.command(name="stop", description="Opreste self-bot-ul")
async def stop_cmd(interaction: discord.Interaction):
    await selfbot.stop()
    config["autopost"]["enabled"] = False
    save_config(config)
    await interaction.response.send_message("Self-bot oprit.", ephemeral=True)


# ==========================================================================
# Server HTTP pentru Render (Web Service) + UptimeRobot
# ==========================================================================
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"bot": "online", "selfbot": selfbot.status}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        return


def start_web():
    port = int(os.getenv("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Health).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        print("[eroare] Lipseste BOT_TOKEN in variabile.")
    else:
        bot.run(bot_token)
