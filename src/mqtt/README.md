# Smart devices over MQTT: every user connects their own ESP32

**English** | [বাংলা](README.bn.md)

One firmware runs on every ESP32. Each user connects their device to **their own Wi-Fi** from a phone, then sees the device's data and controls it on a **web page**. Nobody edits code. Devices talk to the server through an **MQTT broker**.

```
                                  ┌──────────── your computer / server ────────────┐
 ESP32 (esp32.py)  ──Wi-Fi──▶     │  mqtt.py   MQTT broker        :1883            │
   same file on                   │     ▲  ▼                                       │
   every device                   │  server.py  web page + API    :8080            │
                                  │             + memory (lists)                   │
 Phone / browser  ◀───────────────│                                                │
                                  └────────────────────────────────────────────────┘
```

| File | Role |
|------|------|
| [mqtt.py](mqtt.py) | **MQTT broker.** Devices log in with their own secret and can only use their own topics. |
| [server.py](server.py) | **Web page + API server.** Hands out the page ([index.html](index.html)), users, device claiming, stores readings, sends commands. Listens to the broker. |
| [esp32.py](esp32.py) | **Device firmware** (MicroPython). Setup hotspot, Wi-Fi saving, MQTT. |
| [setup_device.py](setup_device.py) | Prepares or updates one device from your computer (USB). |
| [store.py](store.py) | Shared security code and the device list `devices.json` (device IDs + hashes of their secrets). **No database.** |
| [config.py](config.py) | Ports and addresses. |

## How a user sets up a device

1. **Power on** the device. With no Wi-Fi yet, it opens its own hotspot `SmartDevice-XXXX` (LED blinks slowly).
2. On the phone, join that hotspot. The **password is the claim code** printed on the box.
3. A setup page opens by itself (or open `http://192.168.4.1`).
4. Choose your Wi-Fi (2.4 GHz), type its password, press **Save**. The device restarts and joins your Wi-Fi.
5. Reconnect the phone to your normal Wi-Fi and open the web page.
6. **Create an account** (or log in), press **Add device**, enter the **Device ID** and **Claim code** from the box.
7. The device appears with live data. Switch the LED, change how often history is saved, open the history.

To move a device to another Wi-Fi, **hold the BOOT button for 5 seconds**. It forgets the Wi-Fi and returns to step 1.

## Where data is kept

There is **no database**. Users, logins, device owners, live values and history are plain Python lists inside `server.py` (`USERS`, `TOKENS`, `DEVICES`, `READINGS`). **They disappear when `server.py` stops**: after a restart, users register again, devices are claimed again, and history starts empty (the last 20000 readings are kept while it runs). Only `devices.json` survives: it holds each device's ID and the *hashes* of its secret and claim code, so the broker still recognises your devices after a restart.

## Quick start

```bash
source .venv/bin/activate
pipenv install                     # once
```

Start two programs, each in its own terminal, from the project root:

```bash
python src/mqtt/mqtt.py --lan      # 1. broker  (--lan lets devices on your Wi-Fi connect)
python src/mqtt/server.py          # 2. web page + API (port 8080)
```

Each prints its address. Open the address that `server.py` prints on your phone, for example `http://192.168.50.64:8080`. Phone, computer and devices must be on the same Wi-Fi for this test.

**Prepare a device** (board on USB; MicroPython must already be on it). `--host` is the address of this computer **as the device sees it**:

```bash
python src/mqtt/setup_device.py --host 192.168.50.64
```

It prints the label for the box:

```
 Device ID  : esp32-a1b2c3d4e5f6
 Claim code : ABCD-2345
 Setup Wi-Fi: SmartDevice-E5F6 (password = claim code)
```

Labels are also saved in `labels.csv` (private, not in git). Then follow the user steps above.

**Update a device that is already set up** (new firmware or the computer's address changed). It keeps the device's ID, secret, owner and saved Wi-Fi:

```bash
python src/mqtt/setup_device.py --update --host 192.168.50.64
```

To redo a device from scratch (new secret and claim code, Wi-Fi forgotten): `setup_device.py --force --host ...`.

## MQTT topics

Every device uses its own topics, `devices/<device id>/...`

| Topic | Direction | Content |
|-------|-----------|---------|
| `devices/<id>/data` | device → server | `{"temperature":27.5,"humidity":60,"sensor_value":512,"uptime":120,"led":false}` every 5 s |
| `devices/<id>/status` | device → server (retained) | `online` / `offline`. The broker sends `offline` for the device if it loses power or Wi-Fi (MQTT "last will"). |
| `devices/<id>/cmd` | server → device | `{"led":true}` |

## Who may do what on the broker

| Who | Login | Allowed |
|-----|-------|---------|
| a device | its ID + secret | publish its own `data` and `status`, subscribe to its own `cmd`. **Nothing else.** |
| `server.py` | user `server` + a secret in `.server_secret` (created automatically, private) | everything |
| anyone else | – | refused |

Users never touch the broker. They use the web page, which uses the API. A user only sees and controls devices they claimed.

## Web API (used by the web page)

Interactive docs: `http://SERVER:8080/docs`

| Request | Purpose |
|---------|---------|
| `POST /api/register`, `/api/login`, `/api/logout` | Accounts. Login returns a token (`Authorization: Bearer ...`). |
| `GET /api/devices` | The user's own devices with live data. |
| `POST /api/devices/claim` | Add a device: `{"device_id", "claim_code", "name"}`. |
| `GET /api/devices/{id}/history?limit=50` | Stored readings, newest first. |
| `POST /api/devices/{id}/cmd` | `{"led": true}` and/or `{"interval": 30}` (how often history is saved, 5 to 3600 s). |
| `DELETE /api/devices/{id}` | Remove the device from the account (its history is deleted). |
| `GET /api/health` | Is the server running and connected to the broker. |

## Security in this test version

- Passwords are stored as salted hashes. Device secrets and claim codes are stored only as hashes.
- Each device has its own secret and can only touch its own topics.
- Login, register and claim attempts are rate limited. Asking for someone else's device returns "not found".
- The hotspot of a device that is not set up is protected by its claim code.
- `setup_device.py` never keeps a device secret on your computer after copying it to the board.

**Known limitation of the built-in broker.** The `amqtt` broker deletes a client's session as soon as *anyone* connects with the same client id, **before** it checks the password. The attacker is still refused, but the real client stops receiving messages while staying connected. Device IDs are printed on the box, so someone on your network could do this. To limit the damage, `server.py` pings itself and reconnects when the ping does not return (about 30 s), and each device reconnects every 5 minutes. For real customers use **Mosquitto**, which checks the password first.

## Not included yet (needed before real customers)

| Missing | Why it matters |
|---------|----------------|
| **TLS / HTTPS** | Passwords, tokens, secrets and data travel unencrypted. Fine at home for a test; **not** safe on the internet. Put the broker and API behind TLS and use `mqtts` / `https`. |
| **Cloud server** | This test runs on your computer. Users elsewhere need a server with a public address. |
| **Mosquitto in production** | See the limitation above. The rest of this project works the same with it (the per-device password check and topic rules must be set up there). |
| **Saving data while offline** | Readings taken while Wi-Fi or internet is down are lost. |
| **Remote firmware updates (OTA)** | Fixing a bug on 100 devices needs a cable today. |
| **Password reset, email** | Users log in with a username only. |
| **Real sensor** | `read_sensor()` in `esp32.py` returns random numbers. Replace it. |
| **Production flashing script** | `setup_device.py` does one device at a time and needs MicroPython already on the board. |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| The setup hotspot is not visible | Wait 10 seconds after power-on. Check the LED blinks slowly. Hold BOOT for 5 seconds to restart setup. |
| Phone says the hotspot has no internet | Normal. Stay connected; the setup page needs no internet. |
| Setup page does not open by itself | Open `http://192.168.4.1`. |
| After saving, the hotspot comes back | Wrong Wi-Fi name/password, or a 5 GHz-only network. The device returns to setup after 20 seconds. Try again. |
| Device stays "Offline" on the web page | The device must reach the broker: same Wi-Fi, `mqtt.py --lan` running, and `--host` used the computer's current IP. If the IP changed, run `setup_device.py --update --host NEW_IP`. |
| ESP32 prints `Broker refused this device` | The device is not in `devices.json` (for example the file was deleted). Run `setup_device.py --force`. |
| ESP32 prints `Cannot reach the broker` | Broker not running, firewall, or a wrong address. |
| Web page cannot log in / "Cannot reach the server" | `server.py` must be running. The page and the API are served by it on the same address. |
| "Wrong device ID or claim code" | Copy them exactly from the label. The code is not case sensitive. |
| "This device already belongs to another account" | The previous owner must remove it first (or `setup_device.py --force`). |
| "Too many attempts" | Wait a minute. |
| `server.py` says it cannot reach the MQTT broker | Start `mqtt.py` first. |

## What has been tested

On a computer, with the ESP32 hardware simulated: 40 checks of the broker and server (who may connect, topic permissions, accounts, claiming, ownership isolation, commands reaching only the right device, the broker's last will, history, rate limits, CORS, the web page), the firmware's run mode, setup page, DNS, BOOT button, wrong secret, broker down, a kicked session and a power cut.

On the real ESP32: the firmware was installed with `setup_device.py --update` and the device came **online through MQTT** and its data reached the server.

**Not tested yet:** switching the LED from the web page on the real device, and the web page in a phone browser. Test these first.
