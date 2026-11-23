"""Shared helpers for server.py and setup_device.py. No database.

Only ONE thing is kept in a file: devices.json, the list of devices made by
setup_device.py (each device's ID and the HASHES of its secret and claim code).
The server must know it, and a restart must not make 100 devices strangers.

Everything else (users, logins, readings, who owns which device) lives in
plain Python lists inside server.py and is gone when it stops.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# APP_DEVICES lets tests use a separate file; normally it is devices.json next to this file
DEVICES_FILE = os.environ.get("APP_DEVICES") or os.path.join(HERE, "devices.json")

DEFAULT_INTERVAL = 10                   # seconds between stored history points
CLAIM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I confusion
DEVICE_ID_RE = r"^[A-Za-z0-9_-]{1,64}$"

# -------------------------
# HASHING
# -------------------------


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + digest.hex()


def check_password(password, stored):
    salt_hex, _, _ = stored.partition(":")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)


def normalize_code(code):
    return code.replace("-", "").replace(" ", "").upper()


# -------------------------
# DEVICE LIST (devices.json)
# -------------------------


def load_devices():
    """The registered devices: [{id, secret_hash, claim_hash, created}]. Read fresh each
    time, because setup_device.py (another program) may have changed the file."""
    try:
        with open(DEVICES_FILE) as f:
            found = json.load(f)
        return found if isinstance(found, list) else []
    except (OSError, ValueError):
        return []


def save_devices(devices):
    tmp = DEVICES_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(devices, f, indent=2)
    os.replace(tmp, DEVICES_FILE)


def find_device(device_id):
    for d in load_devices():
        if d["id"] == device_id:
            return d
    return None


def register_device(device_id, force=False):
    """Add a device. Returns (secret, claim_code). The secret is only put on the
    device; devices.json keeps just a hash of it."""
    if not re.match(DEVICE_ID_RE, device_id):
        raise ValueError("Invalid device ID: %s" % device_id)

    devices = load_devices()
    if any(d["id"] == device_id for d in devices) and not force:
        raise ValueError("Device %s is already registered (use --force to redo it)." % device_id)

    secret = secrets.token_urlsafe(24)
    claim_code = "".join(secrets.choice(CLAIM_ALPHABET) for _ in range(8))

    devices = [d for d in devices if d["id"] != device_id]
    devices.append({"id": device_id, "secret_hash": sha256(secret),
                    "claim_hash": sha256(claim_code), "created": time.time()})
    save_devices(devices)
    return secret, claim_code


def verify_device(device_id, secret):
    found = find_device(device_id)
    return found is not None and hmac.compare_digest(sha256(secret), found["secret_hash"])
