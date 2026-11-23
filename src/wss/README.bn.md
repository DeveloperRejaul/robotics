# ডিভাইস সার্ভার (Socket.IO / WebSocket)

ESP32 সার্ভারে সেন্সরের ডেটা পাঠায় এবং কমান্ড (LED চালু/বন্ধ) সঙ্গে সঙ্গে পায়। ইউজার ওয়েব পেজে লাইভ আপডেট দেখে ও ডিভাইস চালায়।

আলাদা MQTT ব্রোকার **লাগে না**। একটা `server.py` একই পোর্টে (**8090**) ওয়েব পেজ, API ও Socket.IO দেয়।

English: [README.md](README.md)

## ফাইল

| ফাইল | কোথায় চলে | কাজ |
|---|---|---|
| `server.py` | কম্পিউটার / সার্ভার | ওয়েব পেজ, API, Socket.IO (`/device` ও `/web` namespace) |
| `setup_device.py` | কম্পিউটার (বোর্ড USB তে) | ESP32 প্রস্তুত করে: ID, secret, claim code, ফার্মওয়্যার |
| `esp32.py` | ESP32 | ফার্মওয়্যার (`main.py` নামে বসে) |
| `store.py`, `config.py` | কম্পিউটার | ডিভাইস তালিকা, ইউজার, সাধারণ সেটিং |
| `index.html`, `socket.io.min.js` | ব্রাউজার | ওয়েব পেজ ও Socket.IO ক্লায়েন্ট |

`devices.json`, `labels.json`, `cert.pem`, `key.pem` গোপন, গিটে যায় না।

## কীভাবে কাজ করে

1. `setup_device.py` বোর্ডের নিজস্ব ID পড়ে, secret ও claim code বানায় এবং ফার্মওয়্যার বসায়।
2. ইউজার বোর্ডের নিজের Wi-Fi হটস্পটে যুক্ত হয়ে নিজের Wi-Fi দেয়।
3. বোর্ড সার্ভারে WebSocket খোলে, ID ও secret দিয়ে লগইন করে, প্রতি ৫ সেকেন্ডে ডেটা পাঠায়।
4. ইউজার ওয়েব পেজে রেজিস্টার করে লেবেলের claim code দিয়ে ডিভাইস নিজের করে নেয়।
5. পেজে লাইভ ডেটা আসে (polling নয়) এবং LED চালানো যায়। ডিভাইস ডেটা পাঠানো বন্ধ করলে প্রায় ২০ সেকেন্ডে অফলাইন দেখায়।

ইউজার শুধু নিজের ডিভাইস দেখে। ভুল secret, অচেনা ID ও ভুল টোকেন প্রত্যাখ্যাত হয়। ইউজার ও রিডিং শুধু মেমরিতে থাকে (সার্ভার রিস্টার্টে মুছে যায়), ডিভাইস তালিকা `devices.json` এ থাকে।

## চালানো

```bash
pipenv install

# ১. সার্ভার চালু
python src/wss/server.py            # http://<আপনার-ip>:8090
python src/wss/server.py --tls      # https:// ও wss:// (self-signed সার্টিফিকেট)

# ২. বোর্ড প্রস্তুত (USB), --host হলো ডিভাইস যে ঠিকানায় সার্ভার দেখে
python src/wss/setup_device.py --host 192.168.50.64
python src/wss/setup_device.py --host 192.168.50.64 --tls

# পুরোনো বোর্ডের ফার্মওয়্যার আপডেট (ID, secret, মালিক, Wi-Fi থাকে)
python src/wss/setup_device.py --update --host 192.168.50.64
```

`--tls` দিলে ব্রাউজার সতর্ক করবে: "Advanced" দিয়ে এগোন। সার্ভার ও বোর্ড একই মোডে থাকতে হবে (দুটোই সাধারণ অথবা দুটোই `--tls`)।

বোর্ডের BOOT বোতাম ৫ সেকেন্ড চেপে ধরলে Wi-Fi ভুলে সেটআপ মোডে ফেরে।

## API

API ডকুমেন্ট `/docs` এ। প্রধান রুট: `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/devices`, `POST /api/devices/claim`, `DELETE /api/devices/{id}`, `GET /api/devices/{id}/history`, `POST /api/devices/{id}/cmd`।

Socket.IO ইভেন্ট (namespace `/device`): `data` (ডিভাইস থেকে সার্ভারে), `cmd` (সার্ভার থেকে ডিভাইসে)।
