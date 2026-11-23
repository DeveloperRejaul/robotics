"""API server (runs on your server, next to the MQTT broker).

  * Listens to every device through the MQTT broker (devices/+/data, status),
    and keeps the readings in memory (plain lists, gone when this program stops).
  * Serves the web page (index.html) and the web API it uses:
      users register / log in, claim a device with its ID + claim code,
      see their own devices, read history, send commands.
  * A user can only see and control the devices they own.
  * Commands (LED on/off) are sent to the device through MQTT.

Run:  python src/mqtt/server.py        (the broker, mqtt.py, must be running)
Web page: http://localhost:8080      Interactive API docs: http://localhost:8080/docs
"""

import argparse
import hmac
import json
import math
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

import paho.mqtt.client as paho
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

import config
import store
from store import DEVICE_ID_RE, normalize_code, sha256

# -------------------------
# DATA (plain lists in memory; everything here is lost when the server stops)
# -------------------------

USERS = []      # {"id", "username", "pw_hash", "created"}
TOKENS = []     # {"token_hash", "user_id", "expires"}
DEVICES = []    # live state per device: {"id", "owner_id", "name", "created", "last_seen",
                #   "last_data", "state", "status", "interval", "last_stored"}
READINGS = []   # history: {"device", "ts", "temperature", "humidity", "sensor_value", "uptime"}
MAX_READINGS = 20000
lock = threading.RLock()


def get_device(device_id):
    """The live record of a device that setup_device.py registered (None if unknown)."""
    with lock:
        for d in DEVICES:
            if d["id"] == device_id:
                return d
        registered = store.find_device(device_id)
        if registered is None:
            return None
        d = {"id": device_id, "owner_id": None, "name": None, "created": registered["created"],
             "last_seen": None, "last_data": None, "state": None, "status": None,
             "interval": store.DEFAULT_INTERVAL, "last_stored": 0}
        DEVICES.append(d)
        return d


ONLINE_WITHIN = 20          # seconds: a device counts as online if it was heard this recently
TOKEN_DAYS = 30             # how long a login lasts

settings = {"host": config.BROKER_HOST, "port": config.BROKER_PORT}

SUBSCRIPTIONS = [("devices/+/data", 1), ("devices/+/status", 1), ("server/ping", 0)]
# The broker (amqtt) throws away a client's session as soon as ANYONE connects with the same
# client id, before it checks the password. We would stay connected but stop receiving anything.
# So we ping ourselves regularly and reconnect if the ping does not come back.
HEARTBEAT_SECONDS = float(os.environ.get("HEARTBEAT_SECONDS", "30"))
pong = threading.Event()

# -------------------------
# RATE LIMITS
# -------------------------


class RateLimiter:
    """At most `limit` hits per `window` seconds for each key (kept in memory)."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = {}
        self.lock = threading.Lock()

    def check(self, key):
        now = time.time()
        with self.lock:
            recent = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self.hits[key] = recent
                raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
            recent.append(now)
            self.hits[key] = recent


auth_limiter = RateLimiter(10, 60)    # login / register, per client address
claim_limiter = RateLimiter(10, 60)   # claim attempts, per user

# -------------------------
# MQTT (devices -> server)
# -------------------------


def number(value):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and math.isfinite(value) else None


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print("Broker refused the server:", reason_code)
        return
    print("Connected to the MQTT broker. Listening to all devices.")
    client.subscribe(SUBSCRIPTIONS)  # also after reconnects


def on_message(client, userdata, msg):
    if msg.topic == "server/ping":
        pong.set()
        return
    parts = msg.topic.split("/")  # devices/<id>/<kind>
    if len(parts) != 3:
        return
    _, device_id, kind = parts

    d = get_device(device_id)
    if d is None:
        return  # unknown device: ignore

    try:
        if kind == "status":
            status = msg.payload.decode().strip()
            if status in ("online", "offline"):
                d["status"] = status
                print("[status] %s %s" % (device_id, status))

        elif kind == "data":
            body = json.loads(msg.payload.decode())
            if not isinstance(body, dict):
                return
            now = time.time()
            data = {k: number(body.get(k)) for k in ("temperature", "humidity", "sensor_value", "uptime")}
            state = {"led": bool(body.get("led", False))}
            d.update(last_seen=now, last_data=data, state=state, status="online")

            # Store a history point only every `interval` seconds
            if d["owner_id"] is not None and now - d["last_stored"] >= d["interval"]:
                with lock:
                    READINGS.append({"device": device_id, "ts": now, **{k: data[k] for k in
                                     ("temperature", "humidity", "sensor_value")}, "uptime": data["uptime"]})
                    if len(READINGS) > MAX_READINGS:
                        del READINGS[:len(READINGS) - MAX_READINGS]  # forget the oldest
                    d["last_stored"] = now
    except (ValueError, UnicodeDecodeError):
        print("Ignored a bad message on", msg.topic)


mqtt_client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=store.SERVER_USER)
mqtt_client.username_pw_set(store.SERVER_USER, store.server_secret())
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


def watchdog(stop):
    while not stop.wait(HEARTBEAT_SECONDS):
        if not mqtt_client.is_connected():
            continue
        pong.clear()
        mqtt_client.publish("server/ping", b"1")
        if not pong.wait(3):
            print("The broker stopped delivering messages to us. Reconnecting...")
            try:
                mqtt_client.reconnect()
            except Exception as error:
                print("Reconnect failed:", error)


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    threading.Thread(target=watchdog, args=(stop,), daemon=True).start()
    mqtt_client.loop_start()   # reconnects by itself if the broker restarts
    yield
    stop.set()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()


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
    token_hash, now = sha256(authorization[7:]), time.time()
    with lock:
        TOKENS[:] = [t for t in TOKENS if t["expires"] > now]  # forget expired logins
        token = next((t for t in TOKENS if t["token_hash"] == token_hash), None)
        user = next((u for u in USERS if token and u["id"] == token["user_id"]), None)
    if not user:
        raise HTTPException(401, "Session expired, log in again")
    return user


def new_token(user_id):
    token = secrets.token_urlsafe(32)
    with lock:
        TOKENS.append({"token_hash": sha256(token), "user_id": user_id,
                       "expires": time.time() + TOKEN_DAYS * 86400})
    return token


def device_view(d):
    age = None if d["last_seen"] is None else time.time() - d["last_seen"]
    return {
        "id": d["id"],
        "name": d["name"] or d["id"],
        "online": d["status"] != "offline" and age is not None and age <= ONLINE_WITHIN,
        "age": None if age is None else round(age),
        "last": d["last_data"],
        "state": d["state"],
        "interval": d["interval"],
    }


def owned_device(user, device_id):
    d = get_device(device_id)
    if not d or d["owner_id"] != user["id"]:
        raise HTTPException(404, "Device not found")  # same answer for "not yours"
    return d


# -------------------------
# WEB API
# -------------------------

app = FastAPI(title="Device server", lifespan=lifespan)

# ---- the web page (same server, same address: no CORS needed) ----

INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_FILE, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/config.js", include_in_schema=False)
def page_config():
    # The page and the API share one address, so the page calls the API on its own address.
    return PlainTextResponse('window.API_BASE = "";\n', media_type="application/javascript",
                             headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)



@app.get("/api/health")
def health():
    return {"ok": True, "mqtt_connected": mqtt_client.is_connected()}


# ---- users ----


@app.post("/api/register")
def register(body: Credentials, request: Request):
    auth_limiter.check("reg:" + request.client.host)
    username = body.username.lower()
    pw_hash = store.hash_password(body.password)  # slow on purpose; done before taking the lock
    with lock:
        if any(u["username"] == username for u in USERS):
            raise HTTPException(409, "That username is taken")
        user = {"id": len(USERS) + 1, "username": username, "pw_hash": pw_hash, "created": time.time()}
        USERS.append(user)
    return {"token": new_token(user["id"]), "username": username}


@app.post("/api/login")
def login(body: Credentials, request: Request):
    auth_limiter.check("login:" + request.client.host)
    with lock:
        user = next((u for u in USERS if u["username"] == body.username.lower()), None)
    if not user or not store.check_password(body.password, user["pw_hash"]):
        raise HTTPException(401, "Wrong username or password")
    return {"token": new_token(user["id"]), "username": user["username"]}


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(default=None), user=Depends(current_user)):
    with lock:
        TOKENS[:] = [t for t in TOKENS if t["token_hash"] != sha256(authorization[7:])]
    return {"ok": True}


# ---- devices ----


@app.get("/api/devices")
def list_devices(user=Depends(current_user)):
    with lock:
        mine = sorted((d for d in DEVICES if d["owner_id"] == user["id"]), key=lambda d: d["created"])
        return [device_view(d) for d in mine]


@app.post("/api/devices/claim")
def claim_device(body: Claim, user=Depends(current_user)):
    claim_limiter.check("claim:%d" % user["id"])
    registered = store.find_device(body.device_id)
    code_ok = registered is not None and hmac.compare_digest(
        sha256(normalize_code(body.claim_code)), registered["claim_hash"]
    )
    if not code_ok:
        raise HTTPException(400, "Wrong device ID or claim code")
    with lock:
        d = get_device(body.device_id)
        if d["owner_id"] not in (None, user["id"]):
            raise HTTPException(409, "This device already belongs to another account")
        d["owner_id"] = user["id"]
        if body.name:
            d["name"] = body.name
        return device_view(d)


@app.delete("/api/devices/{device_id}")
def remove_device(device_id: str = Path(pattern=DEVICE_ID_RE), user=Depends(current_user)):
    d = owned_device(user, device_id)
    with lock:
        d["owner_id"] = None
        d["name"] = None
        READINGS[:] = [r for r in READINGS if r["device"] != d["id"]]  # next owner starts clean
    return {"ok": True}


@app.get("/api/devices/{device_id}/history")
def history(
    device_id: str = Path(pattern=DEVICE_ID_RE),
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(current_user),
):
    d = owned_device(user, device_id)
    with lock:
        mine = [r for r in READINGS if r["device"] == d["id"]]
    mine.sort(key=lambda r: r["ts"], reverse=True)  # newest first
    return [{k: r[k] for k in ("ts", "temperature", "humidity", "sensor_value")} for r in mine[:limit]]


@app.post("/api/devices/{device_id}/cmd")
def send_command(
    body: Command,
    device_id: str = Path(pattern=DEVICE_ID_RE),
    user=Depends(current_user),
):
    d = owned_device(user, device_id)
    sent = body.model_dump(exclude_none=True)
    if not sent:
        raise HTTPException(422, "Send at least one of: led, interval")

    if "led" in sent:  # goes to the device through MQTT
        if not mqtt_client.is_connected():
            raise HTTPException(503, "Not connected to the MQTT broker")
        mqtt_client.publish("devices/%s/cmd" % d["id"], json.dumps({"led": sent["led"]}), qos=1)
        print("[cmd]    %s led=%s" % (d["id"], sent["led"]))
    if "interval" in sent:  # how often history is stored (handled here, not on the device)
        d["interval"] = sent["interval"]
    return {"sent": sent}


# -------------------------
# MAIN
# -------------------------


def main():
    parser = argparse.ArgumentParser(description="API server")
    parser.add_argument("--broker-host", default=config.BROKER_HOST, help="MQTT broker address")
    parser.add_argument("--broker-port", type=int, default=config.BROKER_PORT)
    parser.add_argument("--host", default="0.0.0.0", help="API bind address (0.0.0.0 = your Wi-Fi)")
    parser.add_argument("--port", type=int, default=config.WEB_PORT)
    args = parser.parse_args()

    print("Device list:", store.DEVICES_FILE, "(users and readings are kept in memory only)")
    print("Connecting to the MQTT broker %s:%d ..." % (args.broker_host, args.broker_port))
    try:
        mqtt_client.connect(args.broker_host, args.broker_port, keepalive=30)
    except OSError as error:
        print("Cannot reach the MQTT broker:", error)
        print("Start it first:  python src/mqtt/mqtt.py")
        raise SystemExit(1)

    here = config.lan_ip() if args.host == "0.0.0.0" else args.host
    print("Web page:  http://%s:%d" % (here, args.port))
    print("API docs:  http://%s:%d/docs" % (here, args.port))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
