import discord
from discord.ext import commands, tasks
import random
import json
import os
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "user_token": None,
        "autopost": {"enabled": False, "channel_id": None, "base_interval": 240, "message": "Mesaj auto."},
        "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "base_cooldown": 45},
        "cooldowns": {}
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

intents = discord.Intents.default()
intents.message_content = True

class StealthSelfBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", self_bot=True, intents=intents)

    async def on_ready(self):
        print(f"[+] StealthSelfBot ONLINE -> {self.user}")
        if config["autopost"]["enabled"]:
            autopost_loop.start()

    @tasks.loop(minutes=5)  # delay mare
    async def autopost_loop(self):
        if config["autopost"].get("enabled"):
            try:
                channel = self.get_channel(int(config["autopost"]["channel_id"]))
                if channel:
                    content = config["autopost"]["message"] + "‎" * random.randint(0, 7)
                    await asyncio.sleep(random.uniform(1.5, 4.5))
                    if random.random() < 0.6:
                        async with channel.typing():
                            await asyncio.sleep(random.uniform(2, 5))
                    await channel.send(content)
                    print("[+] Autopost sent")
            except Exception as e:
                print(f"[-] Autopost error: {e}")

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return
        # AutoDM stealth
        if config["autodm"]["enabled"] and message.guild is None:
            key = str(message.author.id)
            last = config.get("cooldowns", {}).get(key, 0)
            if time.time() - last > config["autodm"]["base_cooldown"] + random.uniform(25, 55):
                try:
                    await asyncio.sleep(random.uniform(2, 6))
                    await message.author.send(config["autodm"]["message"])
                    config.setdefault("cooldowns", {})[key] = time.time()
                    save_config(config)
                except: pass
        await self.process_commands(message)

    # Exemplu slash
    @discord.app_commands.command(name="status", description="Verifica status")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message("Stealth mode active.", ephemeral=True)

bot = StealthSelfBot()

# Health check pentru Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - SelfBot Running")

def run_health():
    try:
        server = ThreadingHTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), HealthHandler)
        server.serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_health, daemon=True).start()
    bot.run(config["user_token"], bot=False)
