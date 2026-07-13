import discord
from discord.ext import commands, tasks
import random
import json
import os
import time
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from curl_cffi.requests import AsyncSession

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_token": None,
        "autopost": {"enabled": False, "channel_id": None, "base_interval": 300, "message": "Mesaj auto."},
        "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "base_cooldown": 60},
        "cooldowns": {}
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

intents = discord.Intents.default()
intents.message_content = True

class StealthBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", self_bot=True, intents=intents)
        self.http_session = None

    async def setup_hook(self):
        self.http_session = AsyncSession(impersonate="chrome126")
        print("[+] Stealth session initialized (chrome impersonate)")

    async def on_ready(self):
        print(f"[+] SELF BOT ONLINE -> {self.user} | ID: {self.user.id}")
        if config["autopost"].get("enabled"):
            autopost_loop.start()

    @tasks.loop(minutes=5)  # delay mare
    async def autopost_loop(self):
        if config["autopost"].get("enabled"):
            try:
                channel = self.get_channel(int(config["autopost"]["channel_id"]))
                if channel:
                    content = config["autopost"]["message"] + "‎" * random.randint(0, 8)
                    await asyncio.sleep(random.uniform(1.8, 5.2))
                    if random.random() < 0.7:
                        async with channel.typing():
                            await asyncio.sleep(random.uniform(2.8, 7))
                    await channel.send(content)
                    print("[+] Autopost trimis")
            except Exception as e:
                print(f"[-] Autopost error: {e}")

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return
        if config["autodm"].get("enabled") and message.guild is None:
            key = str(message.author.id)
            last = config.get("cooldowns", {}).get(key, 0)
            if time.time() - last > config["autodm"]["base_cooldown"] + random.uniform(30, 70):
                try:
                    await asyncio.sleep(random.uniform(2, 6))
                    await message.author.send(config["autodm"]["message"])
                    config.setdefault("cooldowns", {})[key] = time.time()
                    save_config(config)
                except: pass
        await self.process_commands(message)

    @discord.app_commands.command(name="ping", description="Test stealth")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Stealth mode active.", ephemeral=True)

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

bot = StealthBot()

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - StealthBot Running")

def run_health():
    port = int(os.getenv("PORT", 8080))
    try:
        server = ThreadingHTTPServer(('0.0.0.0', port), HealthHandler)
        server.serve_forever()
    except Exception as e:
        print(e)

if __name__ == "__main__":
    threading.Thread(target=run_health, daemon=True).start()
    bot.run(config["user_token"], bot=False)
