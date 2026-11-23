"""Settings shared by the programs that run on your computer / server
(server.py, setup_device.py).

The ESP32 does NOT read this file. Its own settings (ID, secret, server
address) are written to the board by setup_device.py.
"""

import socket

# -------------------------
# PORTS
# -------------------------

PORT = 8091   # server.py : the web page and the API (devices + browsers), plain HTTP, one port


def lan_ip():
    """This computer's address on your Wi-Fi (what phones and devices use)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; it only picks the interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
