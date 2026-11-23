# ডিভাইস সার্ভার (সাধারণ HTTP)

[../wss](../wss) এর একই কাজ, কিন্তু শুধু সাধারণ HTTP দিয়ে: WebSocket, Socket.IO বা MQTT নেই। সহজ, যেকোনো প্রক্সির পেছনে চলে, `curl` দিয়ে পরীক্ষা করা যায়। দাম হলো সামান্য দেরি: কমান্ড ডিভাইসের পরের রিকোয়েস্টে পৌঁছায় (প্রায় ৩ সেকেন্ডের মধ্যে) আর ওয়েব পেজ প্রতি ২ সেকেন্ডে রিফ্রেশ হয়।

পোর্ট **8091** (যাতে 8090 এর `wss` সার্ভারের পাশে চলতে পারে)। English: [README.md](README.md)

## ফাইল

| ফাইল | কোথায় চলে | কাজ |
|---|---|---|
| `server.py` | কম্পিউটার / সার্ভার | ওয়েব পেজ ও API (ব্রাউজার ও ডিভাইসের জন্য) |
| `setup_device.py` | কম্পিউটার (বোর্ড USB তে) | ESP32 প্রস্তুত করে: ID, secret, claim code, ফার্মওয়্যার |
| `esp32.py` | ESP32 | ফার্মওয়্যার (`main.py` নামে বসে) |
| `store.py`, `config.py` | কম্পিউটার | ডিভাইস তালিকা, ইউজার, সাধারণ সেটিং |
| `index.html` | ব্রাউজার | ওয়েব পেজ (API polling করে) |

`devices.json`, `labels.json`, `cert.pem`, `key.pem` গোপন, গিটে যায় না।

## কীভাবে কাজ করে

1. `setup_device.py` বোর্ডের নিজস্ব ID পড়ে, secret ও claim code বানায় এবং ফার্মওয়্যার বসায়।
2. ইউজার বোর্ডের নিজের Wi-Fi হটস্পটে যুক্ত হয়ে নিজের Wi-Fi দেয়।
3. প্রতি ৩ সেকেন্ডে বোর্ড `POST /api/device/sync` পাঠায়: হেডারে ID ও secret (`X-Device-Id`, `X-Device-Secret`), বডিতে রিডিং (JSON)। উত্তর `{"led": true|false|null}`: অপেক্ষমাণ LED কমান্ড, না থাকলে `null`। ডিভাইস কাজটা করেছে জানানো পর্যন্ত সার্ভার কমান্ডটা বারবার পাঠায়।
4. ইউজার ওয়েব পেজে রেজিস্টার করে লেবেলের claim code দিয়ে ডিভাইস নিজের করে নেয়।
5. পেজ প্রতি ২ সেকেন্ডে `GET /api/devices` করে। ডিভাইস কল বন্ধ করলে প্রায় ২০ সেকেন্ডে অফলাইন দেখায়।

ইউজার শুধু নিজের ডিভাইস দেখে। ভুল secret, অচেনা ID ও ভুল টোকেন প্রত্যাখ্যাত হয়। ইউজার ও রিডিং শুধু মেমরিতে থাকে (সার্ভার রিস্টার্টে মুছে যায়), ডিভাইস তালিকা `devices.json` এ থাকে।

## চালানো

```bash
# ১. সার্ভার চালু
python src/http/server.py            # http://<আপনার-ip>:8091
python src/http/server.py --tls      # https:// (self-signed সার্টিফিকেট)

# ২. বোর্ড প্রস্তুত (USB). --host হলো ডিভাইস যে ঠিকানায় সার্ভার দেখে
python src/http/setup_device.py --host 192.168.50.64
python src/http/setup_device.py --host 192.168.50.64 --tls

# পুরোনো বোর্ডের ফার্মওয়্যার আপডেট (ID, secret, মালিক, Wi-Fi থাকে)
python src/http/setup_device.py --update --host 192.168.50.64
```

সার্ভার ও বোর্ড একই মোডে থাকতে হবে (দুটোই সাধারণ অথবা দুটোই `--tls`)। `--tls` দিলে ব্রাউজার সতর্ক করবে। বোর্ডের BOOT বোতাম ৫ সেকেন্ড চেপে ধরলে Wi-Fi ভুলে যায়।

## API

ডকুমেন্ট `/docs` এ। ডিভাইস: `POST /api/device/sync`। ইউজার: `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/devices`, `POST /api/devices/claim`, `DELETE /api/devices/{id}`, `GET /api/devices/{id}/history`, `POST /api/devices/{id}/cmd`।

বোর্ড ছাড়া পরীক্ষা:
```bash
curl -X POST http://localhost:8091/api/device/sync \
  -H "X-Device-Id: esp32-xxxx" -H "X-Device-Secret: <secret>" \
  -H "Content-Type: application/json" -d '{"temperature":25,"led":false}'
```
