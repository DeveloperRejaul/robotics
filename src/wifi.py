import network
import socket
import time
import ujson
import random

# -------------------------
# CONFIGURATION
# -------------------------

# "AP"  -> the ESP32 creates its own Wi-Fi. Your phone joins it (no router needed).
# "STA" -> the ESP32 joins your home Wi-Fi. Your phone must be on the same Wi-Fi.
MODE = "AP"

DEVICE_NAME = "REJAUL-ESP32"

# AP mode settings (password must be at least 8 characters)
AP_SSID = "REJAUL-ESP32"
AP_PASSWORD = "12345678"

# STA mode settings (your home Wi-Fi)
STA_SSID = "YOUR_WIFI_NAME"
STA_PASSWORD = "YOUR_WIFI_PASSWORD"

PORT = 80

# -------------------------
# WI-FI SETUP
# -------------------------


def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=network.AUTH_WPA2_PSK)
    while not ap.active():
        time.sleep(0.1)
    print("Wi-Fi hotspot started:", AP_SSID)
    return ap.ifconfig()[0]


def start_sta():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(STA_SSID, STA_PASSWORD)

    print("Connecting to", STA_SSID, end="")
    for _ in range(30):
        if wlan.isconnected():
            print()
            return wlan.ifconfig()[0]
        print(".", end="")
        time.sleep(0.5)

    raise RuntimeError("Could not connect to Wi-Fi: " + STA_SSID)


# -------------------------
# DATA
# -------------------------


def read_data():
    # Replace these random values with real sensor readings
    return {
        "device": DEVICE_NAME,
        "temperature": round(random.uniform(20, 40), 2),
        "humidity": round(random.uniform(30, 90), 2),
        "sensor_value": random.randint(0, 1000),
    }


# -------------------------
# WEB PAGE (opens in the phone browser, refreshes every second)
# -------------------------

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ESP32 Data</title>
<style>
body { font-family: sans-serif; padding: 20px; background: #111; color: #eee; }
h1 { font-size: 20px; }
.card { background: #222; border-radius: 12px; padding: 16px; margin: 10px 0; }
.value { font-size: 32px; font-weight: bold; }
</style>
</head>
<body>
<h1 id="device">ESP32</h1>
<div class="card">Temperature<div class="value" id="temperature">-</div></div>
<div class="card">Humidity<div class="value" id="humidity">-</div></div>
<div class="card">Sensor value<div class="value" id="sensor_value">-</div></div>
<script>
async function update() {
  try {
    const d = await (await fetch('/data')).json();
    document.getElementById('device').textContent = d.device;
    document.getElementById('temperature').textContent = d.temperature + ' C';
    document.getElementById('humidity').textContent = d.humidity + ' %';
    document.getElementById('sensor_value').textContent = d.sensor_value;
  } catch (e) {}
}
update();
setInterval(update, 1000);
</script>
</body>
</html>
"""


def respond(client, status, content_type, body):
    client.send("HTTP/1.1 " + status + "\r\n")
    client.send("Content-Type: " + content_type + "\r\n")
    client.send("Access-Control-Allow-Origin: *\r\n")
    client.send("Connection: close\r\n\r\n")
    client.sendall(body)


def handle(client):
    request = client.recv(1024).decode()
    line = request.split("\r\n")[0]  # e.g. "GET /data HTTP/1.1"
    parts = line.split(" ")
    path = parts[1] if len(parts) > 1 else "/"

    if path == "/data":
        message = ujson.dumps(read_data())
        print("Sent:", message)
        respond(client, "200 OK", "application/json", message)
    elif path == "/":
        respond(client, "200 OK", "text/html", PAGE)
    else:
        respond(client, "404 Not Found", "text/plain", "Not found")


# -------------------------
# START
# -------------------------

ip = start_ap() if MODE == "AP" else start_sta()

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", PORT))
server.listen(5)

print("==========================")
print("Wi-Fi server started!")
print("Mode:", MODE)
if MODE == "AP":
    print("Join Wi-Fi:", AP_SSID, "| password:", AP_PASSWORD)
print("Open in phone browser: http://" + ip)
print("JSON data:             http://" + ip + "/data")
print("==========================")

while True:
    client = None
    try:
        client, addr = server.accept()
        client.settimeout(3)
        handle(client)
    except Exception as error:
        print("Request error:", error)
    finally:
        if client:
            client.close()
