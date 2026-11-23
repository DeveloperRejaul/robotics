# Device server (Socket.IO / WebSocket)

An ESP32 sends sensor data to your server and receives commands (LED on/off) instantly. Users watch and control their devices from a web page with live updates.

There is **no separate MQTT broker**. One program, `server.py`, serves the web page, the API and Socket.IO on a single port (**8090**).

Bangla: [README.bn.md](README.bn.md)

## Files

| File | Runs on | Purpose |
|---|---|---|
| `server.py` | computer / server | Web page, API, Socket.IO (`/device` and `/web` namespaces) |
| `setup_device.py` | computer (board on USB) | Prepares an ESP32: ID, secret, claim code, firmware |
| `esp32.py` | ESP32 | Firmware (installed as `main.py`) |
| `store.py`, `config.py` | computer | Device list, users, shared settings |
| `index.html`, `socket.io.min.js` | browser | The web page and its Socket.IO client |

`devices.json`, `labels.json`, `cert.pem` and `key.pem` are private and ignored by git.

## How it works

1. `setup_device.py` reads the board's unique ID, creates a secret and a claim code, and installs the firmware.
2. The user connects to the board's own Wi-Fi hotspot and enters their home Wi-Fi.
3. The board opens a WebSocket to the server, logs in with its ID and secret, and sends data every 5 seconds.
4. The user registers on the web page and claims the device with the claim code (printed on the label).
5. The page shows live readings (no polling) and can switch the LED. A device that stops sending is shown offline after about 20 seconds.

Users only see their own devices. Wrong secrets, unknown IDs and bad tokens are rejected. Users and readings are kept in memory only (lost when the server restarts); the device list is in `devices.json`.

## Run

```bash
pipenv install

# 1. Start the server
python src/wss/server.py            # http://<your-ip>:8090
python src/wss/server.py --tls      # https:// and wss:// (self-signed certificate)

# 2. Prepare a board (USB), --host is the server address as the DEVICE sees it
python src/wss/setup_device.py --host 192.168.50.64
python src/wss/setup_device.py --host 192.168.50.64 --tls

# Update firmware on an existing board (keeps ID, secret, owner, Wi-Fi)
python src/wss/setup_device.py --update --host 192.168.50.64
```

With `--tls` the browser warns about the self-signed certificate: choose "Advanced" and continue. The server and the board must use the same mode (both plain or both `--tls`).

Hold the board's BOOT button for 5 seconds to forget its Wi-Fi and return to setup mode.

## API

API docs are at `/docs`. Main routes: `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/devices`, `POST /api/devices/claim`, `DELETE /api/devices/{id}`, `GET /api/devices/{id}/history`, `POST /api/devices/{id}/cmd`.

Socket.IO events (namespace `/device`): `data` (device to server), `cmd` (server to device).
