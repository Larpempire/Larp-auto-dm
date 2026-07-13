import os
import json
import time
import random
import asyncio
import threading
import websockets
import aiohttp
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG_FILE = "config.json"
DISCORD_API = "https://discord.com/api/v10"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

DEFAULT_CONFIG = {
    "user_token": None,
    "proxies": [],
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 60, "messages": ["Mesaj automat."]},
    "autodm": {"enabled": True, "messages": ["Salut! Momentan nu sunt disponibil."], "cooldown_seconds": 20},
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
        self.seq = 0
        self.running = False
        self.status = "stopped"
        self.proxy_index = 0
        self.last_message_time = 0
        self.heartbeat_task = None

    def get_proxy(self):
        if not config["proxies"]:
            return None
        proxy = config["proxies"][self.proxy_index % len(config["proxies"])]
        self.proxy_index += 1
        return proxy

    async def start(self, token: str):
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
                async with websockets.connect(GATEWAY_URL, ping_interval=None, proxy=proxy) as ws:
                    self.ws = ws
                    await self._identify()
                    await self._gateway_loop()
            except Exception as e:
                print(f"[Gateway Error] {e}")
                await asyncio.sleep(5 + random.random() * 5)

    async def _identify(self):
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": 1 << 9 | 1 << 15,  # Guild messages + Direct messages
                "properties": {
                    "$os": "linux",
                    "$browser": "chrome",
                    "$device": "desktop"
                }
            }
        }
        await self.ws.send(json.dumps(payload))

    async def _gateway_loop(self):
        while self.running:
            msg = await self.ws.recv()
            data = json.loads(msg)

            if data["op"] == 10:  # Hello
                interval = data["d"]["heartbeat_interval"] / 1000
                self.heartbeat_task = asyncio.create_task(self._heartbeat(interval))

            elif data["op"] == 0:  # Dispatch
                self.seq = data.get("s", self.seq)
                if data["t"] == "READY":
                    self.user = data["d"]["user"]
                    self.status = "running"
                    print(f"[+] Logged in as {self.user['username']}")
                    asyncio.create_task(self._autopost_loop())
                elif data["t"] == "MESSAGE_CREATE":
                    await self._on_message(data["d"])

    async def _heartbeat(self, interval):
        while self.running:
            await self.ws.send(json.dumps({"op": 1, "d": self.seq}))
            await asyncio.sleep(interval + random.uniform(-1, 1))

    async def send_message(self, channel_id: str, content: str):
        proxy = self.get_proxy()
        now = time.time()
        if now - self.last_message_time < 8:
            await asyncio.sleep(8)

        # Typing uman
        if random.random() < 0.6:
            try:
                async with self.session.post(
                    f"{DISCORD_API}/channels/{channel_id}/typing",
                    headers={"Authorization": self.token},
                    proxy=proxy
                ): pass
            except:
                pass
            await asyncio.sleep(random.uniform(1.8, 4.2))

        url = f"{DISCORD_API}/channels/{channel_id}/messages"
        headers = {"Authorization": self.token, "Content-Type": "application/json"}

        async with self.session.post(url, headers=headers, json={"content": content}, proxy=proxy) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", 10))
                await asyncio.sleep(retry + random.randint(3, 12))
            elif r.status in (200, 201):
                self.last_message_time = time.time()

    async def _autopost_loop(self):
        while self.running:
            cfg = config["autopost"]
            if cfg.get("enabled") and cfg.get("channel_id"):
                try:
                    msg = random.choice(cfg.get("messages", ["Mesaj automat."]))
                    await self.send_message(cfg["channel_id"], msg)
                except:
                    pass
                await asyncio.sleep(cfg.get("interval_seconds", 60) + random.randint(-12, 18))
            else:
                await asyncio.sleep(30)

    async def _on_message(self, msg):
        if msg.get("guild_id"):
            return  # ignoră serverele dacă vrei doar DMs
        author = msg.get("author", {})
        if not self.user or author.get("id") == self.user.get("id"):
            return
        cfg = config["autodm"]
        if not cfg.get("enabled"):
            return

        user_id = str(author.get("id"))
        now = int(time.time())
        cooldown = cfg.get("cooldown_seconds", 20)
        if now < config["cooldowns"].get(user_id, 0) + cooldown:
            return

        config["cooldowns"][user_id] = now
        save_config(config)

        reply = random.choice(cfg.get("messages", ["Salut!"]))
        await self.send_message(msg["channel_id"], reply)

# Health server simplu
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

def start_health_server():
    server = ThreadingHTTPServer(('0.0.0.0', 8080), HealthHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    token = config.get("user_token") or os.getenv("USER_TOKEN", "").strip()
    if token:
        bot = AdvancedStealthBot()
        asyncio.run(bot.start(token))
    else:
        print("[-] Token lipsă în config.json sau env")
