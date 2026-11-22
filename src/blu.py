import bluetooth
import random
import time
import ujson

from micropython import const

# -------------------------
# CONFIGURATION
# -------------------------

DEVICE_NAME = "REJAUL-ESP32"
BLE_PIN = "1234"      # the phone must write this PIN before it receives data
MAX_TRIES = 3         # wrong PIN attempts before we disconnect the phone

# BLE events
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# -------------------------
# BLE INITIALIZATION
# -------------------------

ble = bluetooth.BLE()
ble.active(True)  # BLE must be active before any ble.config() call

# Allow larger notifications (default MTU 23 only carries 20 bytes)
ble.config(mtu=256)

# Nordic UART Service
UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # phone -> ESP32
TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # ESP32 -> phone

RX = (RX_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE)
TX = (TX_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY)

SERVICE = (UART_UUID, (TX, RX))

((tx_handle, rx_handle),) = ble.gatts_register_services((SERVICE,))

connections = set()   # all connected phones
authed = set()        # phones that sent the correct PIN
tries = {}            # wrong PIN count per connection

# -------------------------
# HELPERS
# -------------------------


def send(conn, text):
    try:
        ble.gatts_notify(conn, tx_handle, text.encode())
    except Exception as error:
        print("Send Error:", error)


# -------------------------
# BLE EVENT HANDLER
# -------------------------


def ble_irq(event, data):
    if event == _IRQ_CENTRAL_CONNECT:
        conn_handle, _, _ = data
        connections.add(conn_handle)
        tries[conn_handle] = 0
        print("Mobile connected, waiting for PIN...")

    elif event == _IRQ_CENTRAL_DISCONNECT:
        conn_handle, _, _ = data
        connections.discard(conn_handle)
        authed.discard(conn_handle)
        tries.pop(conn_handle, None)
        print("Mobile disconnected!")
        advertise()

    elif event == _IRQ_GATTS_WRITE:
        conn_handle, value_handle = data
        if value_handle != rx_handle:
            return

        text = bytes(ble.gatts_read(rx_handle)).decode().strip()

        if conn_handle in authed:
            print("Received:", text)
        elif text == BLE_PIN:
            authed.add(conn_handle)
            print("PIN correct, phone authorized!")
            send(conn_handle, "AUTH_OK")
        else:
            tries[conn_handle] = tries.get(conn_handle, 0) + 1
            print("Wrong PIN (%d/%d)" % (tries[conn_handle], MAX_TRIES))
            send(conn_handle, "AUTH_FAIL")
            if tries[conn_handle] >= MAX_TRIES:
                ble.gap_disconnect(conn_handle)


# -------------------------
# BLE ADVERTISING
# -------------------------


def advertise():
    name = DEVICE_NAME.encode()

    # Advertising data: flags + complete local name
    adv_data = b"\x02\x01\x06" + bytes((len(name) + 1, 0x09)) + name

    # Scan response: 128-bit service UUID (so apps can filter by Nordic UART)
    resp_data = bytes((17, 0x07)) + bytes(UART_UUID)

    ble.gap_advertise(100000, adv_data, resp_data=resp_data)


ble.irq(ble_irq)
advertise()

print("==========================")
print("Bluetooth Started!")
print("Device:", DEVICE_NAME)
print("PIN:", BLE_PIN)
print("==========================")

# -------------------------
# RANDOM DATA GENERATOR
# -------------------------

while True:
    data = {
        "device": DEVICE_NAME,
        "temperature": round(random.uniform(20, 40), 2),
        "humidity": round(random.uniform(30, 90), 2),
        "sensor_value": random.randint(0, 1000),
    }

    message = ujson.dumps(data)
    print("Generated:", message)

    for conn in list(authed):
        send(conn, message)

    time.sleep(1)
