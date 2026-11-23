# Device server (plain HTTP)

Same task as [../wss](../wss), but with ordinary HTTP only: no WebSocket, no Socket.IO, no MQTT. Simple, works behind any proxy, easy to test with `curl`. The price is a small delay: commands reach the device on its next request (within about 3 seconds) and the web page refreshes every 2 seconds.

Port **8091** (so it can run next to the `wss` server on 8090). Bangla: [README.bn.md](README.bn.md)

## Files

| File | Runs on | Purpose |
|---|---|---|
| `server.py` | computer / server | Web page and API (for browsers and devices) |
| `setup_device.py` | computer (board on USB) | Prepares an ESP32: ID, secret, claim code, firmware |
| `esp32.py` | ESP32 | Firmware (installed as `main.py`) |
| `store.py`, `config.py` | computer | Device list, users, shared settings |
| `index.html` | browser | The web page (polls the API) |

`devices.json`, `labels.json`, `cert.pem` and `key.pem` are private and ignored by git.

## How it works

1. `setup_device.py` reads the board's unique ID, creates a secret and a claim code, and installs the firmware.
2. The user connects to the board's own Wi-Fi hotspot and enters their home Wi-Fi.
3. Every 3 seconds the board sends `POST /api/device/sync` with its ID and secret in the headers (`X-Device-Id`, `X-Device-Secret`) and its readings as JSON. The answer is `{"led": true|false|null}`: a pending LED command, or `null` for none. The server repeats a command until the device reports it was done.
4. The user registers on the web page and claims the device with the claim code (on the label).
5. The page polls `GET /api/devices` every 2 seconds. A device that stops calling is shown offline after about 20 seconds.

Users only see their own devices. Wrong secrets, unknown IDs and bad tokens are rejected. Users and readings are kept in memory only (lost when the server restarts); the device list is in `devices.json`.

## Run

```bash
# 1. Start the server
python src/http/server.py            # http://<your-ip>:8091
python src/http/server.py --tls      # https:// (self-signed certificate)

# 2. Prepare a board (USB). --host is the server address as the DEVICE sees it
python src/http/setup_device.py --host 192.168.50.64
python src/http/setup_device.py --host 192.168.50.64 --tls

# Update firmware on an existing board (keeps ID, secret, owner, Wi-Fi)
python src/http/setup_device.py --update --host 192.168.50.64
```

Server and board must use the same mode (both plain or both `--tls`). With `--tls` the browser warns about the self-signed certificate. Hold the board's BOOT button for 5 seconds to forget its Wi-Fi.

## API

Docs at `/docs`. Device: `POST /api/device/sync`. Users: `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/devices`, `POST /api/devices/claim`, `DELETE /api/devices/{id}`, `GET /api/devices/{id}/history`, `POST /api/devices/{id}/cmd`.

Test without a board:
```bash
curl -X POST http://localhost:8091/api/device/sync \
  -H "X-Device-Id: esp32-xxxx" -H "X-Device-Secret: <secret>" \
  -H "Content-Type: application/json" -d '{"temperature":25,"led":false}'
```
