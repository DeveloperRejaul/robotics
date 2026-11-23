"""The server: web page + API + Socket.IO (WebSocket) in ONE program, one port.

  * Devices (ESP32) connect with Socket.IO to the /device namespace and log in with
    their ID + secret. They send readings; the server sends them commands (LED).
  * Browsers connect to the /web namespace with their login token and get live updates.
  * The web API (/api/...) is used by the page: users register / log in, claim a
    device with its ID + claim code, read history, send commands.
  * A user can only see and control the devices they own.
  * Users, logins, readings and live values are plain Python lists in memory
    (gone when this program stops). Only devices.json (device IDs + hashes) is a file.

Run:  python src/wss/server.py            (add --tls for wss:// and https://)
Web page: http://localhost:8090           API docs: http://localhost:8090/docs
"""

import argparse
import asyncio
import hmac
import math
import os
import secrets
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Optional

import socketio
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

import config
import store
from store import DEVICE_ID_RE, normalize_code, sha256

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(HERE, "index.html")
CLIENT_JS = os.path.join(HERE, "socket.io.min.js")

ONLINE_WITHIN = 20          # seconds: a device counts as online if it was heard this recently
TOKEN_DAYS = 30             # how long a login lasts
TICK_SECONDS = 5            # the page also gets a refresh this often (for "last heard" ages)

# -------------------------
# DATA (plain lists in memory; everything here is lost when the server stops)
# -------------------------

USERS = []      # {"id", "username", "pw_hash", "created"}
TOKENS = []     # {"token_hash", "user_id", "expires"}
DEVICES = []    # live state per device: {"id", "owner_id", "name", "created", "last_seen",
                #   "last_data", "state", "status", "interval", "last_stored", "sid"}
READINGS = []   # history: {"device", "ts", "temperature", "humidity", "sensor_value", "uptime"}
MAX_READINGS = 20000

DEVICE_SIDS = {}   # Socket.IO connection id -> device id   (connected devices)
WEB_SIDS = {}      # Socket.IO connection id -> (user id, token hash)   (open browser pages)


def get_device(device_id):
    """The live record of a device that setup_device.py registered (None if unknown)."""
    for d in DEVICES:
        if d["id"] == device_id:
            return d
    registered = store.find_device(device_id)
    if registered is None:
        return None
    d = {"id": device_id, "owner_id": None, "name": None, "created": registered["created"],
         "last_seen": None, "last_data": None, "state": None, "status": None,
         "interval": store.DEFAULT_INTERVAL, "last_stored": 0, "sid": None}
    DEVICES.append(d)
    return d


# -------------------------
# RATE LIMITS
# -------------------------


class RateLimiter:
    """At most `limit` hits per `window` seconds for each key (kept in memory)."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = {}

    def check(self, key):
        now = time.time()
        recent = [t for t in self.hits.get(key, []) if now - t < self.window]
        if len(recent) >= self.limit:
            self.hits[key] = recent
            raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
        recent.append(now)
        self.hits[key] = recent


auth_limiter = RateLimiter(10, 60)    # login / register, per client address
claim_limiter = RateLimiter(10, 60)   # claim attempts, per user

# -------------------------
# SOCKET.IO
# -------------------------

# ping_interval / ping_timeout: a device that vanishes (power cut, Wi-Fi lost) is noticed in
# about 20 seconds and shown as offline.
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[], ping_interval=10, ping_timeout=10)


def number(value):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and math.isfinite(value) else None


def device_view(d):
    age = None if d["last_seen"] is None else time.time() - d["last_seen"]
    return {
        "id": d["id"],
        "name": d["name"] or d["id"],
        "online": d["sid"] is not None and age is not None and age <= ONLINE_WITHIN,
        "age": None if age is None else round(age),
        "last": d["last_data"],
        "state": d["state"],
        "interval": d["interval"],
    }


def devices_of(user_id):
    mine = sorted((d for d in DEVICES if d["owner_id"] == user_id), key=lambda d: d["created"])
    return [device_view(d) for d in mine]


async def push(user_id):
    """Send the user's device list to every open page of that user."""
    if user_id is not None:
        await sio.emit("devices", devices_of(user_id), room="user:%d" % user_id, namespace="/web")


# ---- devices: /device ----


@sio.on("connect", namespace="/device")
async def device_connect(sid, environ, auth):
    device_id = auth.get("id") if isinstance(auth, dict) else None
    secret = auth.get("secret") if isinstance(auth, dict) else None
    if not isinstance(device_id, str) or not isinstance(secret, str) or not store.verify_device(device_id, secret):
        raise socketio.exceptions.ConnectionRefusedError("bad credentials")

    d = get_device(device_id)
    old = d["sid"]
    d["sid"] = sid                    # a new valid login replaces an older connection of the same device
    DEVICE_SIDS[sid] = device_id
    d["status"] = "online"
    print("[device] %s connected" % device_id)
    if old and old != sid:
        DEVICE_SIDS.pop(old, None)
        await sio.disconnect(old, namespace="/device")
    await push(d["owner_id"])


@sio.on("disconnect", namespace="/device")
async def device_disconnect(sid, *reason):
    device_id = DEVICE_SIDS.pop(sid, None)
    d = get_device(device_id) if device_id else None
    if d and d["sid"] == sid:
        d["sid"] = None
        d["status"] = "offline"
        print("[device] %s disconnected" % device_id)
        await push(d["owner_id"])


@sio.on("data", namespace="/device")
async def device_data(sid, body):
    d = get_device(DEVICE_SIDS.get(sid))
    if d is None or not isinstance(body, dict):
        return
    now = time.time()
    data = {k: number(body.get(k)) for k in ("temperature", "humidity", "sensor_value", "uptime")}
    d.update(last_seen=now, last_data=data, state={"led": bool(body.get("led", False))}, status="online")

    # Store a history point only every `interval` seconds, and only for owned devices
    if d["owner_id"] is not None and now - d["last_stored"] >= d["interval"]:
        READINGS.append({"device": d["id"], "ts": now, "temperature": data["temperature"],
                         "humidity": data["humidity"], "sensor_value": data["sensor_value"],
                         "uptime": data["uptime"]})
        if len(READINGS) > MAX_READINGS:
            del READINGS[:len(READINGS) - MAX_READINGS]  # forget the oldest
        d["last_stored"] = now
    await push(d["owner_id"])


# ---- browsers: /web ----


def user_of(token):
    now = time.time()
    TOKENS[:] = [t for t in TOKENS if t["expires"] > now]  # forget expired logins
    found = next((t for t in TOKENS if t["token_hash"] == sha256(token)), None)
    return next((u for u in USERS if found and u["id"] == found["user_id"]), None)


@sio.on("connect", namespace="/web")
async def web_connect(sid, environ, auth):
    token = auth.get("token") if isinstance(auth, dict) else None
    user = user_of(token) if isinstance(token, str) else None
    if not user:
        raise socketio.exceptions.ConnectionRefusedError("not logged in")
    WEB_SIDS[sid] = (user["id"], sha256(token))
    await sio.enter_room(sid, "user:%d" % user["id"], namespace="/web")
    asyncio.create_task(first_list(sid, user["id"]))


async def first_list(sid, user_id):
    await asyncio.sleep(0.2)   # let the connection finish first: a packet sent before that is dropped by the browser
    if sid in WEB_SIDS:
        await sio.emit("devices", devices_of(user_id), to=sid, namespace="/web")


@sio.on("disconnect", namespace="/web")
async def web_disconnect(sid, *reason):
    WEB_SIDS.pop(sid, None)


async def ticker():
    """Now and then, refresh every open page (so "last heard" and offline states stay right)."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        for user_id in {u for u, _ in WEB_SIDS.values()}:
            await push(user_id)


# -------------------------
# API MODELS
# -------------------------


class Credentials(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    password: str = Field(min_length=8, max_length=128)


class Claim(BaseModel):
    device_id: str = Field(pattern=DEVICE_ID_RE)
    claim_code: str = Field(min_length=8, max_length=16)
    name: Optional[str] = Field(default=None, max_length=40)


class Command(BaseModel):
    led: Optional[bool] = None
    interval: Optional[int] = Field(default=None, ge=5, le=3600)


# -------------------------
# AUTH + HELPERS
# -------------------------


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")
    user = user_of(authorization[7:])
    if not user:
        raise HTTPException(401, "Session expired, log in again")
    return user


def new_token(user_id):
    token = secrets.token_urlsafe(32)
    TOKENS.append({"token_hash": sha256(token), "user_id": user_id,
                   "expires": time.time() + TOKEN_DAYS * 86400})
    return token


def owned_device(user, device_id):
    d = get_device(device_id)
    if not d or d["owner_id"] != user["id"]:
        raise HTTPException(404, "Device not found")  # same answer for "not yours"
    return d


# -------------------------
# WEB API + PAGE
# -------------------------


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(ticker())
    yield
    task.cancel()


api = FastAPI(title="Device server", lifespan=lifespan)


@api.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_FILE, media_type="text/html", headers={"Cache-Control": "no-store"})


@api.get("/socket.io.min.js", include_in_schema=False)
def client_js():
    return FileResponse(CLIENT_JS, media_type="application/javascript")


@api.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@api.get("/api/health")
def health():
    return {"ok": True, "devices_connected": len(DEVICE_SIDS)}


# ---- users ----


@api.post("/api/register")
async def register(body: Credentials, request: Request):
    auth_limiter.check("reg:" + request.client.host)
    username = body.username.lower()
    pw_hash = await asyncio.to_thread(store.hash_password, body.password)  # slow on purpose
    if any(u["username"] == username for u in USERS):
        raise HTTPException(409, "That username is taken")
    user = {"id": len(USERS) + 1, "username": username, "pw_hash": pw_hash, "created": time.time()}
    USERS.append(user)
    return {"token": new_token(user["id"]), "username": username}


@api.post("/api/login")
async def login(body: Credentials, request: Request):
    auth_limiter.check("login:" + request.client.host)
    user = next((u for u in USERS if u["username"] == body.username.lower()), None)
    ok = user is not None and await asyncio.to_thread(store.check_password, body.password, user["pw_hash"])
    if not ok:
        raise HTTPException(401, "Wrong username or password")
    return {"token": new_token(user["id"]), "username": user["username"]}


@api.post("/api/logout")
async def logout(authorization: Optional[str] = Header(default=None), user=Depends(current_user)):
    token_hash = sha256(authorization[7:])
    TOKENS[:] = [t for t in TOKENS if t["token_hash"] != token_hash]
    for sid, (_, used) in list(WEB_SIDS.items()):   # close the pages that used this login
        if used == token_hash:
            await sio.disconnect(sid, namespace="/web")
    return {"ok": True}


# ---- devices ----


@api.get("/api/devices")
async def list_devices(user=Depends(current_user)):
    return devices_of(user["id"])


@api.post("/api/devices/claim")
async def claim_device(body: Claim, user=Depends(current_user)):
    claim_limiter.check("claim:%d" % user["id"])
    registered = store.find_device(body.device_id)
    code_ok = registered is not None and hmac.compare_digest(
        sha256(normalize_code(body.claim_code)), registered["claim_hash"]
    )
    if not code_ok:
        raise HTTPException(400, "Wrong device ID or claim code")
    d = get_device(body.device_id)
    if d["owner_id"] not in (None, user["id"]):
        raise HTTPException(409, "This device already belongs to another account")
    d["owner_id"] = user["id"]
    if body.name:
        d["name"] = body.name
    await push(user["id"])
    return device_view(d)


@api.delete("/api/devices/{device_id}")
async def remove_device(device_id: str = Path(pattern=DEVICE_ID_RE), user=Depends(current_user)):
    d = owned_device(user, device_id)
    d["owner_id"] = None
    d["name"] = None
    READINGS[:] = [r for r in READINGS if r["device"] != d["id"]]  # next owner starts clean
    await push(user["id"])
    return {"ok": True}


@api.get("/api/devices/{device_id}/history")
async def history(
    device_id: str = Path(pattern=DEVICE_ID_RE),
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(current_user),
):
    d = owned_device(user, device_id)
    mine = [r for r in READINGS if r["device"] == d["id"]]
    mine.sort(key=lambda r: r["ts"], reverse=True)  # newest first
    return [{k: r[k] for k in ("ts", "temperature", "humidity", "sensor_value")} for r in mine[:limit]]


@api.post("/api/devices/{device_id}/cmd")
async def send_command(
    body: Command,
    device_id: str = Path(pattern=DEVICE_ID_RE),
    user=Depends(current_user),
):
    d = owned_device(user, device_id)
    sent = body.model_dump(exclude_none=True)
    if not sent:
        raise HTTPException(422, "Send at least one of: led, interval")

    if "led" in sent:  # goes to the device through its Socket.IO connection
        if d["sid"] is None:
            raise HTTPException(409, "The device is offline")
        await sio.emit("cmd", {"led": sent["led"]}, to=d["sid"], namespace="/device")
        print("[cmd]    %s led=%s" % (d["id"], sent["led"]))
    if "interval" in sent:  # how often history is stored (handled here, not on the device)
        d["interval"] = sent["interval"]
        await push(user["id"])
    return {"sent": sent}


# Socket.IO answers on /socket.io, everything else goes to the API above
app = socketio.ASGIApp(sio, other_asgi_app=api)

# -------------------------
# MAIN
# -------------------------

CERT_FILE = os.path.join(HERE, "cert.pem")
KEY_FILE = os.path.join(HERE, "key.pem")


def make_certificate(host):
    """A self-signed certificate for tests (needs the openssl program, found on macOS/Linux)."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return
    print("Creating a self-signed certificate (browsers will warn about it)...")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365",
         "-keyout", KEY_FILE, "-out", CERT_FILE, "-subj", "/CN=" + host,
         "-addext", "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost" % host],
        check=True, capture_output=True,
    )
    os.chmod(KEY_FILE, 0o600)


def main():
    parser = argparse.ArgumentParser(description="Device server")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (0.0.0.0 = your Wi-Fi)")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--tls", action="store_true",
                        help="secure: https:// for the page and wss:// for devices (self-signed certificate)")
    args = parser.parse_args()

    here = config.lan_ip() if args.host == "0.0.0.0" else args.host
    ssl = {}
    if args.tls:
        make_certificate(here)
        ssl = {"ssl_certfile": CERT_FILE, "ssl_keyfile": KEY_FILE}
    web, socket_scheme = ("https", "wss") if args.tls else ("http", "ws")

    print("Device list:", store.DEVICES_FILE, "(users and readings are kept in memory only)")
    print("Web page:  %s://%s:%d" % (web, here, args.port))
    print("API docs:  %s://%s:%d/docs" % (web, here, args.port))
    print("Devices connect to: %s://%s:%d/socket.io/" % (socket_scheme, here, args.port))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", **ssl)


if __name__ == "__main__":
    main()
