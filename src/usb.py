import random
import select
import sys
import time
import ujson

import machine

# -------------------------
# CONFIGURATION
# -------------------------
# Same job as blu.py, but over the USB cable (USB serial) instead of Bluetooth.
#
# The computer talks to the ESP32 with plain text LINES (one message per line):
#   computer -> ESP32 :  1234          the PIN (must be sent first)
#                        led on        turn the LED on        (after the PIN)
#                        led off       turn the LED off
#                        bye           log out (a new PIN is needed)
#   ESP32 -> computer :  AUTH_OK / AUTH_FAIL / LOCKED
#                        {"device": ..., "temperature": ..., "led": false}   once a second
#
# Lines that do not start with "{" are status messages, ignore them in your reader.

DEVICE_NAME = "REJAUL-ESP32"
USB_PIN = "1234"      # the computer must send this PIN before it receives data
MAX_TRIES = 3         # wrong PIN attempts before the port is locked for a while
LOCK_SECONDS = 10     # how long it stays locked after too many wrong PINs
LED_PIN = 2
SEND_PERIOD = 1       # seconds between data lines

led = machine.Pin(LED_PIN, machine.Pin.OUT)

# -------------------------
# SERIAL INPUT (non-blocking, line by line)
# -------------------------

poller = select.poll()
poller.register(sys.stdin, select.POLLIN)
buffer = ""


def read_line():
    """One complete line typed/sent by the computer, or None if nothing complete yet."""
    global buffer
    while poller.poll(0):
        char = sys.stdin.read(1)
        if char in ("\n", "\r"):
            line, buffer = buffer.strip(), ""
            if line:
                return line
        elif len(buffer) < 64:
            buffer += char
    return None


def send(text):
    print(text)


# -------------------------
# COMMANDS
# -------------------------

authed = False
tries = 0
locked_until = 0


def handle(text):
    global authed, tries, locked_until

    if time.time() < locked_until:
        send("LOCKED")
        return

    if authed:
        command = text.lower()
        if command == "led on":
            led.value(1)
            send("OK led on")
        elif command == "led off":
            led.value(0)
            send("OK led off")
        elif command == "bye":
            authed = False
            send("BYE")
        else:
            send("ERROR unknown command")
    elif text == USB_PIN:
        authed = True
        tries = 0
        send("AUTH_OK")
    else:
        tries += 1
        send("AUTH_FAIL")
        if tries >= MAX_TRIES:
            tries = 0
            locked_until = time.time() + LOCK_SECONDS


# -------------------------
# MAIN LOOP
# -------------------------

send("USB started: " + DEVICE_NAME)
last_sent = time.ticks_ms()

while True:
    line = read_line()
    if line is not None:
        handle(line)

    if authed and time.ticks_diff(time.ticks_ms(), last_sent) >= SEND_PERIOD * 1000:
        last_sent = time.ticks_ms()
        send(ujson.dumps({
            "device": DEVICE_NAME,
            "temperature": round(random.uniform(20, 40), 2),
            "humidity": round(random.uniform(30, 90), 2),
            "sensor_value": random.randint(0, 1000),
            "led": bool(led.value()),
        }))

    time.sleep_ms(20)
