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
    "user_tokens": {},
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Mesaj auto LARP."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "cooldown_seconds": 86400},
    "cooldowns": {}
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in data: data[key] = default_value
        elif isinstance(default_value, dict):
            for subkey, subvalue in default_value.items():
                data[key].setdefault(subkey, subvalue)
    return data

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()

class StealthSelfBot:
    # ... (păstrează tot codul din versiunea anterioară pentru StealthSelfBot - _init_, start, stop, send_message, _run, _connect, etc.)
    # (ca să nu umplu mesajul, folosește exact ce ți-am dat ultima dată)

    # (copiază întregul class StealthSelfBot de mai sus)

selfbot = StealthSelfBot()

# ====================== MANAGEMENT BOT ======================
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logger.info(f"[+] Management bot online as {bot.user}")
    if config.get("user_tokens"):
        token = list(config["user_tokens"].values())[0]
        if selfbot.status == "stopped":
            await selfbot.start(token)

# === Slash commands (adaugă-le pe ale tale aici) ===

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "status": "alive", 
            "selfbot": selfbot.status, 
            "port": os.getenv("PORT"),
            "timestamp": time.time()
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

def start_health_server():
    port = int(os.getenv("PORT", 8080))   # Respectă exact ce ai setat tu
    logger.info(f"[+] Health server started on port {port} (Render should be happy)")
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    
    bot_token = os.getenv("BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
    if bot_token:
        bot.run(bot_token)
    else:
        logger.error("[-] BOT_TOKEN or DISCORD_TOKEN missing in env vars!")
