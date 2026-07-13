import os
import json
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

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)s | %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

config = {
    "user_token": os.getenv("USER_TOKEN"),  # vom seta prin env pentru test
    "proxies": ["http://46.47.197.210:3128"],
    "autopost": {"enabled": True, "channel_id": "ID_CHANNEL_AICI", "message": "Test from auto DM"}
}

class Stealth:
    def __init__(self):
        self.session = None

    async def send(self, channel_id, content):
        proxy = random.choice(config["proxies"])
        logger.info(f"[TEST SEND] to {channel_id} via {proxy}")
        try:
            async with self.session.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": config["user_token"], "Content-Type": "application/json"},
                json={"content": content},
                proxy=proxy
            ) as r:
                logger.info(f"Status: {r.status}")
        except Exception as e:
            logger.error(f"Error: {e}")

    async def loop(self):
        while True:
            await self.send(config["autopost"]["channel_id"], config["autopost"]["message"])
            await asyncio.sleep(30)

stealth = Stealth()

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"[+] Bot online as {bot.user}")
    stealth.session = aiohttp.ClientSession()
    asyncio.create_task(stealth.loop())

def health():
    port = int(os.getenv("PORT", 8080))
    from http.server import HTTPServer
    HTTPServer(("0.0.0.0", port), BaseHTTPRequestHandler).serve_forever()

threading.Thread(target=health, daemon=True).start()

bot.run(os.getenv("BOT_TOKEN"))
