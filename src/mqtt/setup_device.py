"""Prepare an ESP32 for a customer (run on your computer, board on USB).

New device:
  1. Reads the board's unique ID (from its hardware, nothing to type).
  2. Registers it in devices.json and creates its secret and claim code.
  3. Installs the MQTT library, device.json and the firmware (esp32.py as main.py).
  4. Forgets any saved Wi-Fi and restarts the board into setup mode.
  5. Prints the label: Device ID + claim code (put these on the box / QR code).

Update an existing device (keeps its ID, secret, owner and saved Wi-Fi):
  python src/mqtt/setup_device.py --update --host 192.168.50.64

Run:  python src/mqtt/setup_device.py --host 192.168.50.64
      --host is the address of the computer running mqtt.py, as the DEVICE sees it.
"""

import argparse
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import config
import store

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_FILE = os.path.join(HERE, "labels.csv")
LABELS_JSON = os.path.join(HERE, "labels.json")


def mpremote(port, *args, check=True):
    command = [sys.executable, "-m", "mpremote", "connect", port, *args]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if check and result.returncode != 0:
        raise SystemExit("mpremote failed: %s\n%s" % (" ".join(args), result.stderr.strip()))
    return result.stdout.strip()


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*") + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        raise SystemExit("No ESP32 found. Plug it in with a USB DATA cable (or pass --port).")
    return ports[0]


def ensure_mqtt_library(port):
    """The firmware needs umqtt.simple on the board (installed once)."""
    check = subprocess.run(
        [sys.executable, "-m", "mpremote", "connect", port, "exec", "import umqtt.simple"],
        capture_output=True, text=True, timeout=60,
    )
    if check.returncode != 0:
        print("Installing the MQTT library on the board (needs internet on this computer)...")
        mpremote(port, "mip", "install", "umqtt.simple")


def main():
    parser = argparse.ArgumentParser(description="Provision an ESP32")
    parser.add_argument("--host", default=config.lan_ip(),
                        help="address of the computer running mqtt.py, as the DEVICE sees it")
    parser.add_argument("--port", default=None, help="serial port (default: auto-detect)")
    parser.add_argument("--update", action="store_true",
                        help="update an already provisioned device: keep its ID, secret and Wi-Fi")
    parser.add_argument("--force", action="store_true", help="redo a device that is already registered")
    args = parser.parse_args()

    port = args.port or find_port()
    print("Board on", port)
    ensure_mqtt_library(port)

    workdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(workdir, "device.json")

        if args.update:
            # keep everything the board already has; only point it at the broker
            raw = mpremote(port, "cat", ":device.json")
            try:
                device = json.loads(raw)
            except ValueError:
                raise SystemExit("This board has no device.json yet. Run without --update.")
            if not store.find_device(device["id"]):
                raise SystemExit("%s is not in devices.json. Run without --update (add --force)." % device["id"])
            device.pop("server_host", None)
            device.pop("server_port", None)
            device["broker_host"] = args.host
            device["broker_port"] = config.BROKER_PORT
            with open(config_path, "w") as f:
                json.dump(device, f)
            print("Updating", device["id"])
        else:
            uid = mpremote(port, "exec",
                           "import machine, ubinascii; print(ubinascii.hexlify(machine.unique_id()).decode())")
            device_id = "esp32-" + uid.splitlines()[-1].strip()
            print("Device ID:", device_id)
            try:
                secret, claim_code = store.register_device(device_id, force=args.force)
            except ValueError as error:
                raise SystemExit(str(error))
            device = {
                "id": device_id,
                "secret": secret,
                "claim_code": claim_code,
                "broker_host": args.host,
                "broker_port": config.BROKER_PORT,
            }
            with open(config_path, "w") as f:
                json.dump(device, f)

        print("Copying files to the board...")
        mpremote(port, "cp", config_path, ":device.json")
        mpremote(port, "cp", os.path.join(HERE, "esp32.py"), ":main.py")
        if not args.update:
            mpremote(port, "exec", "import os\ntry: os.remove('wifi.json')\nexcept OSError: pass")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # the secret must not stay on this computer

    mpremote(port, "reset", check=False)
    time.sleep(1)

    if args.update:
        print("\nDone. The board restarts and uses its saved Wi-Fi.")
        return

    new_file = not os.path.exists(LABELS_FILE)
    with open(LABELS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["device_id", "claim_code"])
        writer.writerow([device["id"], device["claim_code"]])

    code = device["claim_code"][:4] + "-" + device["claim_code"][4:]
    labels = []
    try:
        with open(LABELS_JSON) as f:
            labels = json.load(f)
    except (OSError, ValueError):
        pass
    labels = [l for l in labels if l["device_id"] != device["id"]] + [{"device_id": device["id"], "claim_code": code}]
    with open(LABELS_JSON, "w") as f:
        json.dump(labels, f, indent=2)
    print()
    print("=" * 44)
    print(" LABEL FOR THE BOX")
    print("   Device ID  :", device["id"])
    print("   Claim code :", code)
    print("   Setup Wi-Fi: SmartDevice-" + device["id"][-4:].upper(), "(password = claim code)")
    print("=" * 44)
    print("Saved in", LABELS_FILE, "(keep it private)")


if __name__ == "__main__":
    main()
