"""Settings shared by the programs that run on your computer / server
(mqtt.py, server.py, setup_device.py).

The ESP32 does NOT read this file. Its own settings (ID, secret, broker
address) are written to the board by setup_device.py.
"""

import socket

# -------------------------
# PORTS
# -------------------------

BROKER_PORT = 1883   # mqtt.py   : MQTT broker (devices connect here)
WEB_PORT = 8080      # server.py : the web page AND the API (one address for both)

# -------------------------
# WHERE THINGS ARE
# -------------------------

# Address server.py uses to reach the broker. Both run on the same machine.
BROKER_HOST = "127.0.0.1"


def lan_ip():
    """This computer's address on your Wi-Fi (what phones and devices use)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; it only picks the interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
