import os
import json
import asyncio
import datetime
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord  # discord.py-self
from dotenv import load_dotenv

# NOTA: Self-bot-urile incalca Termenii de Serviciu Discord si pot duce
# la banarea contului. Folosesti pe propria raspundere.

load_dotenv()

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

DEFAULT_CONFIG = {
    "autopost": {
        "enabled": False,
        "channel_id": None,
        "interval_seconds": 3600,
        "message": "Mesaj automat.",
    },
    "autodm": {
        "enabled": True,
        "message": "Salut! Momentan nu sunt disponibil, revin cat pot.",
        "cooldown_seconds": 86400,
    },
}


# --------------------------------------------------------------------------
# Config & state (persistente in JSON)
# --------------------------------------------------------------------------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # completeaza cheile lipsa cu valori default
    for key, val in DEFAULT_CONFIG.items():
        data.setdefault(key, val)
        for sub in val:
            data[key].setdefault(sub, val[sub])
    return data


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


config = load_config()
bot = discord.Client()
_bot_ready = False


# --------------------------------------------------------------------------
# Server HTTP pentru Render + UptimeRobot (tine serviciul treaz 24/7)
# --------------------------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "online" if _bot_ready else "starting"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return  # fara log-uri zgomotoase de la ping-uri


def start_web_server():
    port = int(os.getenv("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()
    print(f"[web] Server pornit pe portul {port}")


# --------------------------------------------------------------------------
# Auto-post pe canal, la interval
# --------------------------------------------------------------------------
async def autopost_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        cfg = config["autopost"]
        if cfg.get("enabled") and cfg.get("channel_id"):
            try:
                channel = bot.get_channel(int(cfg["channel_id"]))
                if channel is None:
                    channel = await bot.fetch_channel(int(cfg["channel_id"]))
                await channel.send(cfg["message"])
                print(f"[autopost] Trimis in #{getattr(channel, 'name', cfg['channel_id'])}")
            except Exception as e:
                print(f"[autopost] Eroare: {e}")
            await asyncio.sleep(max(5, int(cfg.get("interval_seconds", 3600))))
        else:
            await asyncio.sleep(10)  # asteptam pana e activat


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------
@bot.event
async def on_ready():
    global _bot_ready
    _bot_ready = True
    print(f"[ok] Logat ca {bot.user.name} ({bot.user.id})")
    bot.loop.create_task(autopost_loop())


@bot.event
async def on_message(message):
    # Comanda de configurare (o dai tu, din contul tau)
    if message.author == bot.user:
        if message.content.strip().lower().startswith("!autoconfig"):
            await run_autoconfig(message)
        return

    # Auto-answer DM
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm(message)


# --------------------------------------------------------------------------
# Auto-answer DM cu cooldown per persoana
# --------------------------------------------------------------------------
async def handle_dm(message):
    cfg = config["autodm"]
    if not cfg.get("enabled"):
        return

    state = load_state()
    author_id = str(message.author.id)
    now_ts = int(datetime.datetime.now().timestamp())
    cooldown = int(cfg.get("cooldown_seconds", 86400))

    last_ts = state.get(author_id, 0)
    if now_ts < last_ts + cooldown:
        remaining = (last_ts + cooldown) - now_ts
        print(f"[dm] Cooldown activ pentru {message.author.name} ({remaining}s ramase)")
        return

    state[author_id] = now_ts
    save_state(state)

    try:
        await message.channel.send(cfg["message"])
        print(f"[dm] Raspuns trimis catre {message.author.name} ({author_id})")
    except Exception as e:
        print(f"[dm] Eroare la trimitere: {e}")


# --------------------------------------------------------------------------
# /autoconfig  (interactiv, in DM cu tine insuti sau in orice chat)
# --------------------------------------------------------------------------
async def ask(message, question, timeout=120):
    await message.channel.send(question)

    def check(m):
        return m.author == bot.user and m.channel == message.channel and m.content.strip().lower() != "!autoconfig"

    try:
        reply = await bot.wait_for("message", check=check, timeout=timeout)
        return reply.content.strip()
    except asyncio.TimeoutError:
        await message.channel.send("Timp expirat. Reia cu !autoconfig")
        return None


async def run_autoconfig(message):
    await message.channel.send(
        "**AUTOCONFIG** — raspunde la intrebari (scrie tu raspunsurile in acest chat).\n"
        "Scrie `skip` ca sa lasi valoarea actuala."
    )

    # 1. Canal pentru auto-post
    ans = await ask(message, "1) ID-ul canalului pe care sa postez automat? (ex: 123456789012345678)")
    if ans is None:
        return
    if ans.lower() != "skip":
        config["autopost"]["channel_id"] = ans.strip()

    # 2. Interval
    ans = await ask(message, "2) La ce interval sa postez? (in secunde, ex: 3600 = 1 ora)")
    if ans is None:
        return
    if ans.lower() != "skip" and ans.isdigit():
        config["autopost"]["interval_seconds"] = int(ans)

    # 3. Mesaj auto-post
    ans = await ask(message, "3) Ce mesaj sa postez automat pe canal?")
    if ans is None:
        return
    if ans.lower() != "skip":
        config["autopost"]["message"] = ans
    config["autopost"]["enabled"] = True

    # 4. Mesaj auto-DM
    ans = await ask(message, "4) Ce mesaj sa trimit automat la DM?")
    if ans is None:
        return
    if ans.lower() != "skip":
        config["autodm"]["message"] = ans

    # 5. Cooldown DM per persoana
    ans = await ask(message, "5) Cooldown per persoana la DM? (in secunde, ex: 5 = raspunde din nou dupa 5 sec)")
    if ans is None:
        return
    if ans.lower() != "skip" and ans.isdigit():
        config["autodm"]["cooldown_seconds"] = int(ans)
    config["autodm"]["enabled"] = True

    save_config(config)
    await message.channel.send(
        "**Configurare salvata!**\n"
        f"- Canal auto-post: `{config['autopost']['channel_id']}`\n"
        f"- Interval: `{config['autopost']['interval_seconds']}s`\n"
        f"- Mesaj post: `{config['autopost']['message']}`\n"
        f"- Mesaj DM: `{config['autodm']['message']}`\n"
        f"- Cooldown DM: `{config['autodm']['cooldown_seconds']}s`"
    )


# --------------------------------------------------------------------------
# Start
# --------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_web_server, daemon=True).start()
    token = os.getenv("TOKEN", "")
    if not token:
        print("[eroare] Lipseste TOKEN. Adauga-l in variabilele de mediu.")
    else:
        bot.run(token)
