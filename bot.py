import os
import json
import asyncio
import datetime
import threading

import discord  # discord.py-self
from flask import Flask, request, jsonify, Response

# NOTA: Self-bot-urile incalca Termenii Discord si pot duce la ban.
# Folosesti pe propria raspundere.

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

DEFAULT_CONFIG = {
    "autopost": {"enabled": False, "channel_id": None, "interval_seconds": 3600, "message": "Mesaj automat."},
    "autodm": {"enabled": True, "message": "Salut! Momentan nu sunt disponibil.", "cooldown_seconds": 86400},
}

# ---------------- Config & state persistente ----------------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        data.setdefault(k, v)
        for sub in v:
            data[k].setdefault(sub, v[sub])
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

# ---------------- Managerul botului Discord ----------------
status = {"state": "stopped", "user": None, "avatar": None, "error": None}
_client = None
_loop = None
_thread = None

def register_events(client):
    @client.event
    async def on_ready():
        status["state"] = "online"
        status["error"] = None
        status["user"] = f"{client.user.name}"
        status["avatar"] = str(client.user.avatar.url) if client.user.avatar else None
        print(f"[ok] Logat ca {client.user.name} ({client.user.id})")
        client.loop.create_task(autopost_loop(client))

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if isinstance(message.channel, discord.DMChannel):
            await handle_dm(client, message)

async def autopost_loop(client):
    await client.wait_until_ready()
    while not client.is_closed():
        cfg = config["autopost"]
        if cfg.get("enabled") and cfg.get("channel_id"):
            try:
                ch = client.get_channel(int(cfg["channel_id"])) or await client.fetch_channel(int(cfg["channel_id"]))
                await ch.send(cfg["message"])
                print(f"[autopost] Trimis pe {cfg['channel_id']}")
            except Exception as e:
                print(f"[autopost] Eroare: {e}")
            await asyncio.sleep(max(5, int(cfg.get("interval_seconds", 3600))))
        else:
            await asyncio.sleep(10)

async def handle_dm(client, message):
    cfg = config["autodm"]
    if not cfg.get("enabled"):
        return
    state = load_state()
    aid = str(message.author.id)
    now = int(datetime.datetime.now().timestamp())
    cd = int(cfg.get("cooldown_seconds", 86400))
    if now < state.get(aid, 0) + cd:
        print(f"[dm] Cooldown activ pentru {message.author.name}")
        return
    state[aid] = now
    save_state(state)
    try:
        await message.channel.send(cfg["message"])
        print(f"[dm] Raspuns trimis catre {message.author.name} ({aid})")
    except Exception as e:
        print(f"[dm] Eroare: {e}")

def _run_bot(token):
    global _client, _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _client = discord.Client()
    register_events(_client)
    try:
        _loop.run_until_complete(_client.start(token))
    except discord.LoginFailure:
        status["state"] = "error"
        status["error"] = "Token invalid"
        print("[eroare] Token invalid")
    except Exception as e:
        status["state"] = "error"
        status["error"] = str(e)
        print(f"[eroare] {e}")
    finally:
        try:
            _loop.close()
        except Exception:
            pass

def start_bot(token):
    global _thread
    stop_bot()
    status["state"] = "starting"
    status["error"] = None
    _thread = threading.Thread(target=_run_bot, args=(token,), daemon=True)
    _thread.start()

def stop_bot():
    global _client, _loop
    if _client and _loop and not _loop.is_closed():
        try:
            fut = asyncio.run_coroutine_threadsafe(_client.close(), _loop)
            fut.result(timeout=10)
        except Exception:
            pass
    _client = None
    status["state"] = "stopped"
    status["user"] = None
    status["avatar"] = None

# ---------------- Panoul web (Flask) ----------------
app = Flask(__name__)

@app.route("/")
def index():
    return Response(PANEL_HTML, mimetype="text/html")

@app.route("/api/status")
def api_status():
    return jsonify(status)

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json(force=True)
        for section in ("autopost", "autodm"):
            if section in data:
                config[section].update(data[section])
        save_config(config)
        return jsonify({"ok": True, "config": config})
    return jsonify(config)

@app.route("/api/start", methods=["POST"])
def api_start():
    token = (request.get_json(force=True) or {}).get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Lipseste tokenul"}), 400
    start_bot(token)
    return jsonify({"ok": True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_bot()
    return jsonify({"ok": True})

# ---------------- HTML panou ----------------
PANEL_HTML = """<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Self-bot Panel</title>
<style>
:root{--bg:#1e1f22;--card:#2b2d31;--muted:#949ba4;--text:#f2f3f5;--accent:#5865f2;--green:#23a55a;--red:#f23f43;--input:#1e1f22}
*{box-sizing:border-box;font-family:system-ui,Segoe UI,Roboto,sans-serif}
body{margin:0;background:var(--bg);color:var(--text);padding:16px}
.wrap{max-width:520px;margin:0 auto}
h1{font-size:20px;margin:8px 0 16px}
.card{background:var(--card);border-radius:12px;padding:16px;margin-bottom:16px}
label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
input,textarea{width:100%;background:var(--input);border:1px solid #111;border-radius:8px;color:var(--text);padding:12px;font-size:16px}
textarea{min-height:70px;resize:vertical}
button{border:0;border-radius:8px;padding:12px 16px;font-size:15px;font-weight:600;cursor:pointer;color:#fff;min-height:44px}
.btn-primary{background:var(--accent)}.btn-green{background:var(--green)}.btn-red{background:var(--red)}
.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1}
.profile{display:flex;align-items:center;gap:12px;margin-top:12px}
.avatar{width:64px;height:64px;border-radius:50%;object-fit:cover;border:3px solid var(--green);background:#111}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.muted{color:var(--muted);font-size:13px}
</style></head><body><div class="wrap">
<h1>Self-bot Control Panel</h1>

<div class="card">
  <label>Token cont (user token)</label>
  <input id="token" type="password" placeholder="Lipeste tokenul aici">
  <div class="row" style="margin-top:12px">
    <button class="btn-green" onclick="startBot()">Start</button>
    <button class="btn-red" onclick="stopBot()">Stop</button>
  </div>
  <div id="statusBox" class="profile"><span class="muted">Stare: neconectat</span></div>
</div>

<div class="card">
  <h1 style="font-size:16px">Auto-post pe canal</h1>
  <label>ID canal</label><input id="channel_id" placeholder="123456789012345678">
  <label>Interval (secunde)</label><input id="interval_seconds" type="number" value="3600">
  <label>Mesaj</label><textarea id="ap_message"></textarea>
</div>

<div class="card">
  <h1 style="font-size:16px">Auto-answer DM</h1>
  <label>Mesaj raspuns DM</label><textarea id="dm_message"></textarea>
  <label>Cooldown per persoana (secunde)</label><input id="cooldown_seconds" type="number" value="86400">
</div>

<button class="btn-primary" style="width:100%" onclick="saveConfig()">Salveaza configurarea</button>
<p class="muted" style="margin-top:12px">Self-bot-urile incalca ToS Discord. Folosesti pe propria raspundere.</p>
</div>
<script>
async function refresh(){
  const s = await (await fetch('/api/status')).json();
  const box = document.getElementById('statusBox');
  const colors = {online:'#23a55a',starting:'#f0b232',stopped:'#949ba4',error:'#f23f43'};
  let html = '<span><span class="dot" style="background:'+(colors[s.state]||'#949ba4')+'"></span>Stare: '+s.state+'</span>';
  if(s.user){ html = '<img class="avatar" src="'+(s.avatar||'')+'" alt="avatar"><div><b>'+s.user+'</b><br><span class="muted">'+s.state+'</span></div>'; }
  if(s.error){ html += '<div class="muted" style="color:#f23f43">'+s.error+'</div>'; }
  box.innerHTML = html;
}
async function loadConfig(){
  const c = await (await fetch('/api/config')).json();
  channel_id.value=c.autopost.channel_id||''; interval_seconds.value=c.autopost.interval_seconds;
  ap_message.value=c.autopost.message; dm_message.value=c.autodm.message; cooldown_seconds.value=c.autodm.cooldown_seconds;
}
async function saveConfig(){
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    autopost:{enabled:true,channel_id:channel_id.value.trim()||null,interval_seconds:+interval_seconds.value,message:ap_message.value},
    autodm:{enabled:true,message:dm_message.value,cooldown_seconds:+cooldown_seconds.value}
  })});
  alert('Configurare salvata');
}
async function startBot(){
  const r = await (await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token.value.trim()})})).json();
  if(!r.ok) alert(r.error||'Eroare'); setTimeout(refresh,1500);
}
async function stopBot(){ await fetch('/api/stop',{method:'POST'}); refresh(); }
loadConfig(); refresh(); setInterval(refresh,3000);
</script></body></html>"""

# ---------------- Start ----------------
if __name__ == "__main__":
    # Auto-start daca ai pus TOKEN in variabile (optional)
    env_token = os.getenv("TOKEN", "").strip()
    if env_token:
        start_bot(env_token)
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
