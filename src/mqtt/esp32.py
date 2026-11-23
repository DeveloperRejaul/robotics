"""ESP32 firmware (MicroPython). The same file runs on every device.

Per-device data lives in files on the board, NOT in this code:
  device.json  id, secret, claim code, broker address   (written by setup_device.py)
  wifi.json    the user's Wi-Fi name + password         (written by the setup page)

Flow:
  1. No saved Wi-Fi (or it fails)  -> SETUP MODE: the device opens its own
     Wi-Fi hotspot with a setup page. The user picks their Wi-Fi and enters the
     password. The device saves it and restarts.
  2. Saved Wi-Fi works             -> RUN MODE: the device logs in to the MQTT
     broker with its ID + secret, publishes sensor data every few seconds and
     receives commands (LED on/off) instantly.
  3. Hold the BOOT button for 5 seconds -> forget the Wi-Fi and go back to setup.

MQTT topics (all start with devices/<id>/):
  data    device -> server   sensor readings (JSON)
  status  device -> server   "online" / "offline" (the broker sends "offline" for us)
  cmd     server -> device   commands, e.g. {"led": true}

LED (GPIO 2):  slow blink = setup mode, fast blink = connecting,
               in run mode it shows the LED command from the web page.
"""

import json
import os
import random
import select
import socket
import time

import machine
import network
from umqtt.simple import MQTTClient, MQTTException

# -------------------------
# SETTINGS
# -------------------------

CONFIG_FILE = "device.json"
WIFI_FILE = "wifi.json"

LED_PIN = 2
BUTTON_PIN = 0           # the BOOT button on most ESP32 boards
PUBLISH_PERIOD = 5       # seconds between sensor readings
KEEPALIVE = 30           # seconds; the broker marks us offline if silent this long
RECONNECT_EVERY = 300    # seconds; reconnect now and then (the broker may drop our session)
CONNECT_TIMEOUT = 20     # seconds to wait for Wi-Fi
PORTAL_RETRY = 600       # setup mode with saved Wi-Fi: try it again after this many seconds (the hotspot is off while trying)
AP_IP = "192.168.4.1"

# -------------------------
# HARDWARE
# -------------------------

led = machine.Pin(LED_PIN, machine.Pin.OUT)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

cfg = {}
_pressed_since = None


def blink(period_ms):
    """Non-blocking blink: call often; the LED follows the clock."""
    led.value(1 if (time.ticks_ms() // period_ms) % 2 else 0)


def check_button():
    """Hold BOOT for 5 seconds: forget the Wi-Fi and restart into setup mode."""
    global _pressed_since
    if button.value() == 0:
        now = time.ticks_ms()
        if _pressed_since is None:
            _pressed_since = now
        elif time.ticks_diff(now, _pressed_since) >= cfg.get("reset_hold_ms", 5000):
            print("Button held: forgetting Wi-Fi")
            try:
                os.remove(WIFI_FILE)
            except OSError:
                pass
            for _ in range(10):
                led.value(1 - led.value())
                time.sleep_ms(80)
            machine.reset()
    else:
        _pressed_since = None


# -------------------------
# FILES
# -------------------------


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


# -------------------------
# WI-FI
# -------------------------


def connect_wifi(sta, wifi, timeout=CONNECT_TIMEOUT):
    sta.active(True)
    if sta.isconnected():
        return True
    print("Connecting to Wi-Fi:", wifi["ssid"])
    sta.connect(wifi["ssid"], wifi.get("password", ""))

    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout * 1000:
        if sta.isconnected():
            print("Wi-Fi connected, IP:", sta.ifconfig()[0])
            return True
        blink(200)  # fast blink
        check_button()
        time.sleep_ms(50)

    print("Wi-Fi failed")
    sta.disconnect()
    return False


# -------------------------
# SENSOR
# -------------------------


def read_sensor():
    # Replace with your real sensor code
    return {
        "temperature": round(random.uniform(20, 40), 2),
        "humidity": round(random.uniform(30, 90), 2),
        "sensor_value": random.randint(0, 1000),
        "uptime": time.ticks_ms() // 1000,
        "led": bool(led.value()),
    }


# -------------------------
# MQTT
# -------------------------

client = None
publish_now = False


def on_message(topic, payload):
    """A command from the web page, for example {"led": true}."""
    global publish_now
    try:
        command = json.loads(payload)
    except ValueError:
        return
    if isinstance(command, dict) and "led" in command:
        led.value(1 if command["led"] else 0)
        print("Command: led", "on" if command["led"] else "off")
        publish_now = True  # report the new state right away


def connect_mqtt():
    global client
    base = "devices/" + cfg["id"] + "/"
    c = MQTTClient(
        client_id=cfg["id"],
        server=cfg["broker_host"],
        port=cfg.get("broker_port", 1883),
        user=cfg["id"],
        password=cfg["secret"],
        keepalive=KEEPALIVE,
    )
    c.set_last_will(base + "status", b"offline", retain=True)  # sent by the broker if we vanish
    c.set_callback(on_message)
    c.connect()                       # raises if the broker is down or refuses us
    c.subscribe(base + "cmd", qos=1)
    c.publish(base + "status", b"online", retain=True)
    client = c                        # only now do we count as connected
    print("MQTT connected to", cfg["broker_host"])


def pause(seconds):
    """Wait, but keep watching the BOOT button."""
    end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        check_button()
        time.sleep_ms(50)


def run_mode(sta, wifi):
    global client, publish_now
    print("Run mode. Device:", cfg["id"])
    led.value(0)
    base = "devices/" + cfg["id"] + "/"
    last_publish = last_ping = last_connect = time.ticks_ms()

    while True:
        check_button()

        if not sta.isconnected():
            print("Wi-Fi lost, reconnecting...")
            client = None
            connect_wifi(sta, wifi)  # keeps trying forever

        if client is None:
            try:
                connect_mqtt()
                last_connect = time.ticks_ms()
                publish_now = True
            except MQTTException as error:  # wrong ID/secret (device not registered)
                print("Broker refused this device:", error)
                pause(15)
                continue
            except Exception as error:      # broker down, timeout, ...
                print("Cannot reach the broker:", error)
                pause(5)
                continue

        try:
            client.check_msg()  # commands arrive here

            now = time.ticks_ms()
            if publish_now or time.ticks_diff(now, last_publish) >= PUBLISH_PERIOD * 1000:
                client.publish(base + "data", json.dumps(read_sensor()))
                last_publish = last_ping = now
                publish_now = False
            elif time.ticks_diff(now, last_ping) >= KEEPALIVE * 500:
                client.ping()
                last_ping = now

            if time.ticks_diff(now, last_connect) >= cfg.get("reconnect_ms", RECONNECT_EVERY * 1000):
                client.disconnect()  # a fresh session also heals a session the broker dropped
                client = None
        except Exception as error:
            print("MQTT lost:", error)
            client = None

        time.sleep_ms(50)


# -------------------------
# SETUP MODE (hotspot + web page + captive DNS)
# -------------------------


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def url_decode(text):
    data = text.replace("+", " ").encode()
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 37 and i + 2 < len(data):  # "%XX"
            try:
                out.append(int(data[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(data[i])
        i += 1
    try:
        return bytes(out).decode()
    except Exception:
        return ""


def parse_form(body):
    form = {}
    for pair in body.split("&"):
        key, _, value = pair.partition("=")
        form[url_decode(key)] = url_decode(value)
    return form


PAGE = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Device setup</title><style>
body{font-family:sans-serif;max-width:420px;margin:24px auto;padding:0 16px;background:#111;color:#eee}
input,select,button{width:100%%;box-sizing:border-box;padding:12px;margin:6px 0 14px;font-size:16px;border-radius:8px;border:1px solid #555;background:#222;color:#eee}
button{background:#2d7ff9;border:0;font-weight:bold}small{color:#aaa}</style></head><body>
<h2>Connect your device to Wi-Fi</h2><small>Device %s</small>
<form method="POST" action="/save">
<label>Your Wi-Fi network (2.4 GHz)</label>
<select name="ssid_list"><option value="">-- choose --</option>%s</select>
<label>...or type its name</label><input name="ssid_manual" autocomplete="off">
<label>Wi-Fi password</label><input name="password" type="password" autocomplete="off">
<button type="submit">Save and connect</button></form>
<small>Network not listed? Type its name above. Only 2.4 GHz Wi-Fi works.</small>
</body></html>"""

DONE = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:sans-serif;max-width:420px;margin:24px auto;padding:0 16px;background:#111;color:#eee}</style></head>
<body><h2>Saved</h2><p>The device is restarting and connecting to <b>%s</b>.
Reconnect your phone to your normal Wi-Fi and open the website to see your device.</p></body></html>"""

BAD = """<!DOCTYPE html><html><body style="font-family:sans-serif;background:#111;color:#eee;padding:24px">
<h2>Please choose or type a Wi-Fi name</h2><p><a style="color:#6af" href="/">Back</a></p></body></html>"""


def scan_networks():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    try:
        found = sta.scan()
    except OSError:
        found = []
    best = {}
    for net in found:
        try:
            ssid = net[0].decode()
        except Exception:
            continue
        if ssid and (ssid not in best or net[3] > best[ssid]):
            best[ssid] = net[3]
    return sorted(best, key=lambda s: -best[s])[:15]


def send_http(conn, status, body):
    head = "HTTP/1.0 %s\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
    data = body.encode()
    conn.sendall((head % (status, len(data))).encode())
    conn.sendall(data)


def read_request(conn):
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 2048:
        chunk = conn.recv(512)
        if not chunk:
            break
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    parts = lines[0].split(" ")
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"
    length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":")[1])
    while len(body) < length and len(body) < 2048:
        chunk = conn.recv(512)
        if not chunk:
            break
        body += chunk
    return method, path, body.decode()


def handle_portal_client(listener, networks):
    conn, _ = listener.accept()
    conn.settimeout(3)
    try:
        method, path, body = read_request(conn)
        if method == "POST" and path == "/save":
            form = parse_form(body)
            ssid = form.get("ssid_manual", "").strip() or form.get("ssid_list", "").strip()
            if not ssid:
                send_http(conn, "400 Bad Request", BAD)
                return
            save_json(WIFI_FILE, {"ssid": ssid, "password": form.get("password", "")})
            send_http(conn, "200 OK", DONE % escape(ssid))
            conn.close()
            print("Wi-Fi saved:", ssid)
            time.sleep(1)
            machine.reset()
        else:
            # Any other path (including phones' "is there internet?" checks)
            # gets the setup page, so the phone opens it automatically.
            options = "".join('<option value="%s">%s</option>' % (escape(n), escape(n)) for n in networks)
            send_http(conn, "200 OK", PAGE % (escape(cfg["id"]), options))
    except Exception as error:
        print("Portal request error:", error)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def answer_dns(dns, here):
    """Answer every DNS question with our own address (captive portal)."""
    query, client = dns.recvfrom(512)
    if len(query) < 12:
        return
    end = 12
    while end < len(query) and query[end] != 0:
        end += query[end] + 1
    question = query[12:end + 5]  # name + type + class
    ip = bytes(int(p) for p in here.split("."))
    reply = (
        query[:2] + b"\x81\x80" + b"\x00\x01\x00\x01\x00\x00\x00\x00"
        + question
        + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ip
    )
    dns.sendto(reply, client)


def setup_mode(has_wifi):
    print("Setup mode")
    networks = scan_networks()

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    name = "SmartDevice-" + cfg["id"][-4:].upper()
    ap.config(essid=name, password=cfg["claim_code"], authmode=network.AUTH_WPA2_PSK)
    print("Hotspot:", name, "| password: the claim code on the box")
    print("Open http://%s if the page does not appear by itself" % AP_IP)

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", cfg.get("portal_port", 80)))
    listener.listen(3)

    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(("0.0.0.0", cfg.get("dns_port", 53)))

    poller = select.poll()
    poller.register(listener, select.POLLIN)
    poller.register(dns, select.POLLIN)

    started = time.ticks_ms()
    while True:
        check_button()
        blink(1000)  # slow blink

        for sock, _ in poller.poll(100):
            if sock is listener:
                handle_portal_client(listener, networks)
            else:
                try:
                    answer_dns(dns, AP_IP)
                except Exception as error:
                    print("DNS error:", error)

        # Saved Wi-Fi but it failed at boot (router was off?): try again later
        if has_wifi and time.ticks_diff(time.ticks_ms(), started) > PORTAL_RETRY * 1000:
            print("Retrying saved Wi-Fi")
            machine.reset()


# -------------------------
# START
# -------------------------


def main():
    global cfg
    cfg = load_json(CONFIG_FILE) or {}

    if not cfg.get("id") or not cfg.get("secret") or not cfg.get("broker_host"):
        print("device.json is missing or old. Run setup_device.py from your computer.")
        while True:
            blink(100)
            check_button()
            time.sleep_ms(20)

    print("Device:", cfg["id"])
    wifi = load_json(WIFI_FILE)
    sta = network.WLAN(network.STA_IF)

    if wifi and connect_wifi(sta, wifi):
        run_mode(sta, wifi)
    else:
        setup_mode(has_wifi=bool(wifi))


main()
