"""The server: web page + API for devices and browsers, plain HTTP, ONE program, one port.

  * Devices (ESP32) call POST /api/device/sync every few seconds with their ID + secret
    (headers). They send their readings; the answer carries the commands (LED).
  * The web page polls GET /api/devices every 2 seconds with its login token.
  * The web API (/api/...) is used by the page: users register / log in, claim a
    device with its ID + claim code, read history, send commands.
  * A user can only see and control the devices they own.
  * Users, logins, readings and live values are plain Python lists in memory
    (gone when this program stops). Only devices.json (device IDs + hashes) is a file.

Run:  python src/http/server.py            (add --tls for https://)
Web page: http://localhost:8091           API docs: http://localhost:8091/docs
"""

import argparse
import asyncio
import hmac
import math
import os
import secrets
import subprocess
import time
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

import config
import store
from store import DEVICE_ID_RE, normalize_code, sha256

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(HERE, "index.html")

ONLINE_WITHIN = 20          # seconds: a device counts as online if it was heard this recently
TOKEN_DAYS = 30             # how long a login lasts

# -------------------------
# DATA (plain lists in memory; everything here is lost when the server stops)
# -------------------------

USERS = []      # {"id", "username", "pw_hash", "created"}
TOKENS = []     # {"token_hash", "user_id", "expires"}
DEVICES = []    # live state per device: {"id", "owner_id", "name", "created", "last_seen",
                #   "last_data", "state", "status", "interval", "last_stored", "want_led"}
READINGS = []   # history: {"device", "ts", "temperature", "humidity", "sensor_value", "uptime"}
MAX_READINGS = 20000


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
         "interval": store.DEFAULT_INTERVAL, "last_stored": 0, "want_led": None}
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
# DEVICES + READINGS
# -------------------------


def number(value):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and math.isfinite(value) else None


def device_view(d):
    age = None if d["last_seen"] is None else time.time() - d["last_seen"]
    return {
        "id": d["id"],
        "name": d["name"] or d["id"],
        "online": age is not None and age <= ONLINE_WITHIN,
        "age": None if age is None else round(age),
        "last": d["last_data"],
        "state": d["state"],
        "interval": d["interval"],
    }


def devices_of(user_id):
    mine = sorted((d for d in DEVICES if d["owner_id"] == user_id), key=lambda d: d["created"])
    return [device_view(d) for d in mine]


def user_of(token):
    now = time.time()
    TOKENS[:] = [t for t in TOKENS if t["expires"] > now]  # forget expired logins
    found = next((t for t in TOKENS if t["token_hash"] == sha256(token)), None)
    return next((u for u in USERS if found and u["id"] == found["user_id"]), None)


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


class DeviceData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    sensor_value: Optional[float] = None
    uptime: Optional[float] = None
    led: bool = False


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


api = FastAPI(title="Device server (HTTP)")


@api.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_FILE, media_type="text/html", headers={"Cache-Control": "no-store"})


@api.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@api.get("/api/health")
def health():
    now = time.time()
    return {"ok": True, "devices_connected": sum(1 for d in DEVICES if d["last_seen"] and now - d["last_seen"] <= ONLINE_WITHIN)}


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
    return {"ok": True}


# ---- the device calls this ----


@api.post("/api/device/sync")
async def device_sync(
    body: DeviceData,
    x_device_id: Optional[str] = Header(default=None),
    x_device_secret: Optional[str] = Header(default=None),
):
    """The device sends its readings; the answer says what the LED should be (or null)."""
    if not x_device_id or not x_device_secret or not store.verify_device(x_device_id, x_device_secret):
        raise HTTPException(401, "bad credentials")
    d = get_device(x_device_id)
    now = time.time()
    if d["last_seen"] is None or now - d["last_seen"] > ONLINE_WITHIN:
        print("[device] %s online" % d["id"])
    data = {k: number(getattr(body, k)) for k in ("temperature", "humidity", "sensor_value", "uptime")}
    d.update(last_seen=now, last_data=data, state={"led": body.led}, status="online")
    if d["want_led"] is not None and d["want_led"] == body.led:
        d["want_led"] = None          # the device did what was asked

    # Store a history point only every `interval` seconds, and only for owned devices
    if d["owner_id"] is not None and now - d["last_stored"] >= d["interval"]:
        READINGS.append({"device": d["id"], "ts": now, **data})
        if len(READINGS) > MAX_READINGS:
            del READINGS[:len(READINGS) - MAX_READINGS]  # forget the oldest
        d["last_stored"] = now
    return {"led": d["want_led"]}


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
    return device_view(d)


@api.delete("/api/devices/{device_id}")
async def remove_device(device_id: str = Path(pattern=DEVICE_ID_RE), user=Depends(current_user)):
    d = owned_device(user, device_id)
    d["owner_id"] = None
    d["name"] = None
    READINGS[:] = [r for r in READINGS if r["device"] != d["id"]]  # next owner starts clean
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

    if "led" in sent:  # the device picks it up with its next sync (within a few seconds)
        if not device_view(d)["online"]:
            raise HTTPException(409, "The device is offline")
        d["want_led"] = sent["led"]
        print("[cmd]    %s led=%s" % (d["id"], sent["led"]))
    if "interval" in sent:  # how often history is stored (handled here, not on the device)
        d["interval"] = sent["interval"]
    return {"sent": sent}


app = api

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
                        help="secure: https:// for the page and the devices (self-signed certificate)")
    args = parser.parse_args()

    here = config.lan_ip() if args.host == "0.0.0.0" else args.host
    ssl = {}
    if args.tls:
        make_certificate(here)
        ssl = {"ssl_certfile": CERT_FILE, "ssl_keyfile": KEY_FILE}
    web = "https" if args.tls else "http"

    print("Device list:", store.DEVICES_FILE, "(users and readings are kept in memory only)")
    print("Web page:  %s://%s:%d" % (web, here, args.port))
    print("API docs:  %s://%s:%d/docs" % (web, here, args.port))
    print("Devices call:       %s://%s:%d/api/device/sync" % (web, here, args.port))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", **ssl)


if __name__ == "__main__":
    main()
