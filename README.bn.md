# রোবোটিক্স প্রজেক্ট: ESP32 এ MicroPython

[English](README.md) | **বাংলা**

ESP32 এ **MicroPython** দিয়ে রোবোটিক্স শেখার একটি নতুনদের উপযোগী ওয়ার্কস্পেস। কোড আসল বোর্ডে চালানো যায়, অথবা VS Code এর ভেতরে Wokwi সিমুলেটরে চালানো যায়, তখন কোনো হার্ডওয়্যার লাগে না।

## কুইক স্টার্ট

ESP32 এ MicroPython আগেই ফ্ল্যাশ করা আছে? চার ধাপে চালু করুন। (প্রথমবার হলে একবার [MicroPython ফার্মওয়্যার ফ্ল্যাশ](#micropython-ফার্মওয়্যার-ফ্ল্যাশ) করে নিন।)

**১. প্রজেক্ট তৈরি**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pipenv
pipenv install
mkdir -p src
```

**২. কোড লেখা।** `src/main.py` ফাইল বানান:

```python
from machine import Pin
from time import sleep

led = Pin(2, Pin.OUT)

while True:
    led.value(not led.value())  # LED উল্টে দেওয়া (toggle)
    sleep(0.5)
```

**৩. ডিভাইস কানেক্ট করা।** USB **ডেটা** ক্যাবল দিয়ে ESP32 লাগান, তারপর পোর্ট খুঁজুন:

```bash
ls /dev/cu.*
PORT=/dev/cu.usbserial-XXXXXXXX   # আপনার পোর্ট দিন
```

**৪. কোড চালানো**

```bash
mpremote connect $PORT run src/main.py
```

LED জ্বলবে-নিভবে। থামাতে `Ctrl + C` চাপুন। প্রোগ্রাম বোর্ডে স্থায়ীভাবে রাখতে চাইলে [প্রোগ্রাম চালানো](#প্রোগ্রাম-চালানো) দেখুন। বোর্ড না থাকলে [সিমুলেটর](#সিমুলেটর-vs-code-এ-wokwi) ব্যবহার করুন।

## সূচিপত্র

1. [কুইক স্টার্ট](#কুইক-স্টার্ট)
2. [প্রয়োজনীয় জিনিস](#প্রয়োজনীয়-জিনিস)
3. [প্রজেক্ট কাঠামো](#প্রজেক্ট-কাঠামো)
4. [সেটআপ](#সেটআপ)
5. [আসল ডিভাইসের সাথে কাজ](#আসল-ডিভাইসের-সাথে-কাজ)
6. [MicroPython ফার্মওয়্যার ফ্ল্যাশ](#micropython-ফার্মওয়্যার-ফ্ল্যাশ)
7. [উদাহরণ: LED ব্লিংক](#উদাহরণ-led-ব্লিংক)
8. [প্রোগ্রাম চালানো](#প্রোগ্রাম-চালানো)
9. [VS Code সেটআপ](#vs-code-সেটআপ)
10. [সিমুলেটর (VS Code এ Wokwi)](#সিমুলেটর-vs-code-এ-wokwi)
11. [সমস্যা সমাধান](#সমস্যা-সমাধান)

## প্রয়োজনীয় জিনিস

| জিনিস | মন্তব্য |
|-------|---------|
| Python 3 | `Pipfile` এ `3.15` চাওয়া আছে। আপনার ভার্সন আলাদা হলে `python_version` বদলে নিন। |
| ESP32 বোর্ড | ঐচ্ছিক। বোর্ড ছাড়াও সিমুলেটরে কাজ চলে। |
| USB **ডেটা** ক্যাবল | শুধু চার্জ করা যায় এমন ক্যাবলে কাজ হবে না। |
| VS Code | সুপারিশকৃত, Python ও Wokwi এক্সটেনশনসহ। |

## প্রজেক্ট কাঠামো

```text
robotics/
├── Pipfile                # Python নির্ভরতা
├── Pipfile.lock
├── README.md              # ইংরেজি ডকুমেন্ট
├── README.bn.md           # বাংলা ডকুমেন্ট (এই ফাইল)
├── src/
│   └── main.py            # আপনার প্রোগ্রাম
└── simulator/
    └── esp32/             # Wokwi কনফিগ: wokwi.toml, diagram.json, ফার্মওয়্যার .bin
```

> `src/` ও `simulator/` ফোল্ডার এখনো রিপোজিটরিতে নেই। নিচের ধাপ অনুসরণ করার সময় এগুলো বানিয়ে নিন।

## সেটআপ

### ১. ভার্চুয়াল এনভায়রনমেন্ট তৈরি

```bash
python3 -m venv .venv
```

### ২. সক্রিয় করা

```bash
source .venv/bin/activate
```

### ৩. সক্রিয় হয়েছে কি না যাচাই

```bash
which python3
# প্রত্যাশিত ফল: <প্রজেক্টের পথ>/.venv/bin/python3
```

### ৪. pipenv ও প্রজেক্টের প্যাকেজ ইনস্টল

```bash
pip install pipenv
pipenv install
```

### ৫. প্যাকেজ ইনস্টল (শুধু নতুন Pipfile শুরু করলে)

```bash
pipenv install esptool mpremote
pipenv install --dev micropython-esp32-stubs
```

| প্যাকেজ | কাজ |
|---------|-----|
| `esptool` | ESP32 চিপ ফ্ল্যাশ করা ও তথ্য দেখা |
| `mpremote` | MicroPython বোর্ডে কোড চালানো ও ফাইল কপি করা |
| `micropython-esp32-stubs` | টাইপ স্টাব, যাতে VS Code `machine` ইত্যাদি মডিউল চিনতে পারে |

## আসল ডিভাইসের সাথে কাজ

### সিরিয়াল পোর্ট খোঁজা

USB ডেটা ক্যাবল দিয়ে ESP32 লাগান, তারপর চালান:

```bash
ls /dev/cu.*
```

`/dev/cu.usbserial-XXXXXXXX` ধরনের নাম খুঁজুন। নিচের উদাহরণে `/dev/cu.usbserial-59450705951` ব্যবহার করা হয়েছে। এটা আপনার নিজের পোর্ট দিয়ে বদলে নিন।

> টিপ: একবার ভেরিয়েবলে রেখে দিন: `PORT=/dev/cu.usbserial-59450705951`, তারপর কমান্ডে `$PORT` ব্যবহার করুন।

### বোর্ডের তথ্য দেখা

নিচের `esptool` কমান্ডগুলো MicroPython **ছাড়াই** কাজ করে:

| উদ্দেশ্য | কমান্ড |
|----------|--------|
| চিপের ধরন, ফিচার, ক্রিস্টাল ফ্রিকোয়েন্সি, MAC | `esptool --port $PORT chip-id` |
| ফ্ল্যাশ মেমোরির সাইজ ও ধরন | `esptool --port $PORT flash-id` |
| MAC অ্যাড্রেস | `esptool --port $PORT read-mac` |

নিচের `mpremote` কমান্ডগুলো কাজ করতে MicroPython **আগে থেকে ফ্ল্যাশ করা** লাগে:

| উদ্দেশ্য | কমান্ড |
|----------|--------|
| কানেক্টেড ডিভাইসের তালিকা | `mpremote devs` |
| MicroPython ভার্সন ও বোর্ডের তথ্য | `mpremote connect $PORT exec "import os; print(os.uname())"` |
| বোর্ডের ফাইল তালিকা | `mpremote connect $PORT ls` |
| ফ্রি RAM ও CPU ফ্রিকোয়েন্সি | `mpremote connect $PORT exec "import gc, machine; print('free RAM:', gc.mem_free()); print('CPU Hz:', machine.freq())"` |

## MicroPython ফার্মওয়্যার ফ্ল্যাশ

প্রতিটি বোর্ডে এটি একবারই করতে হয়।

1. <https://micropython.org/download/ESP32_GENERIC/> থেকে সর্বশেষ stable `.bin` ডাউনলোড করুন।
2. ফ্ল্যাশ মুছুন। **এতে বোর্ডের সব ডেটা মুছে যাবে।**
   ```bash
   esptool --port $PORT erase-flash
   ```
3. ফার্মওয়্যার লিখুন। ডাউনলোড করা ফাইলের নামের সাথে মিলিয়ে নিন।
   ```bash
   esptool --port $PORT --baud 460800 write-flash 0x1000 ~/Downloads/ESP32_GENERIC-*.bin
   ```
4. পরীক্ষা করুন:
   ```bash
   mpremote connect $PORT exec "print('hello')"
   ```
   `hello` ছাপা হলে ফ্ল্যাশ সফল।

## উদাহরণ: LED ব্লিংক

এটা `src/main.py` নামে সেভ করুন। কোডটি **GPIO 2** এর LED প্রতি আধা সেকেন্ডে জ্বালায় ও নেভায়। বেশিরভাগ ESP32 ডেভ বোর্ডে GPIO 2 ই বিল্ট-ইন LED।

```python
from machine import Pin
from time import sleep

led = Pin(2, Pin.OUT)  # GPIO 2 কে আউটপুট হিসেবে নেওয়া

while True:
    led.value(1)   # LED জ্বলবে
    sleep(0.5)
    led.value(0)   # LED নিভবে
    sleep(0.5)
```

বাইরের LED এর তার সংযোগ: GPIO 2 → 220 Ω রেজিস্টর → LED anode (লম্বা পা), LED cathode (ছোট পা) → GND।

চালানোর কমান্ড [প্রোগ্রাম চালানো](#প্রোগ্রাম-চালানো) অংশে আছে।

## প্রোগ্রাম চালানো

আপনার প্রোগ্রাম `src/main.py` তে থাকে। অন্য ফাইল চালাতে নিচের কমান্ডে `src/main.py` এর জায়গায় সেই ফাইলের পথ দিন।

**একবার চালিয়ে দেখা।** বোর্ডে সেভ হয় না। থামাতে `Ctrl + C` চাপুন।

```bash
mpremote connect $PORT run src/main.py
```

**স্থায়ীভাবে সেভ করা।** পাওয়ার দিলেই প্রোগ্রাম নিজে চলবে।

```bash
mpremote connect $PORT cp src/main.py :main.py
mpremote connect $PORT reset
```

**LED বন্ধ করা** (GPIO 2):

```bash
mpremote connect $PORT exec "from machine import Pin; Pin(2, Pin.OUT).value(0)"
```

## VS Code সেটআপ

`Import "machine" could not be resolved` ওয়ার্নিং দূর করতে `micropython-esp32-stubs` ইনস্টল থাকতে হবে। `pipenv install --dev` এটা করে দেয়। তারপর:

1. `Cmd + Shift + P` চেপে **Python: Select Interpreter** চালান।
2. `.venv` ইন্টারপ্রেটার বেছে নিন।
3. **Developer: Reload Window** চালান।

## সিমুলেটর (VS Code এ Wokwi)

আসল বোর্ড ছাড়াই VS Code এর ভেতরে ESP32 চালানো যায়। সিমুলেটরের ফাইল `simulator/esp32/` এ থাকে: `wokwi.toml`, `diagram.json` ও MicroPython ফার্মওয়্যার। `diagram.json` এ ESP32, LED ও 220 Ω রেজিস্টর **GPIO 2** তে জোড়া আছে।

### ব্রাউজারে দ্রুত চেষ্টা

1. <https://wokwi.com> এ গিয়ে নতুন **ESP32 → MicroPython** প্রজেক্ট শুরু করুন।
2. `src/main.py` এর কোড `main.py` তে বসিয়ে ▶ চাপুন।
3. LED লাগান ডান পাশের **2** লেখা পিনে (GPIO 2), 220 Ω রেজিস্টর দিয়ে। অন্য পা GND তে দিন।

> বাঁ পাশের **D2** আসলে GPIO 9। ওটা ব্যবহার করবেন না।

### VS Code এ একবারের সেটআপ

1. **Wokwi for VS Code** এক্সটেনশন ইনস্টল করুন।
2. `F1` চেপে **Wokwi: Request a new License** চালান। ব্রাউজারে ফ্রি লাইসেন্স নিয়ে VS Code এ নিশ্চিত করুন।
3. ফার্মওয়্যার না থাকলে ডাউনলোড করুন (এটা git এ নেই):
   ```bash
   curl -L -o simulator/esp32/ESP32_GENERIC-20260824-v1.29.0.bin \
     https://github.com/wokwi/wokwi-vscode-micropython/raw/main/esp32/ESP32_GENERIC-20260824-v1.29.0.bin
   ```
   ফার্মওয়্যারের ভার্সন (1.29.0) ও `mpremote` এর ভার্সন (1.29.0) মেলানো আছে। `pipenv install --dev` করলে দুটোই মিলে থাকে।

### প্রতিবার চালানোর নিয়ম (পরীক্ষিত, কাজ করছে)

1. VS Code এ `simulator/esp32/diagram.json` খুলুন।
2. **▶ Start Simulation** চাপুন, অথবা `F1` চেপে **Wokwi: Start Simulator** চালান। কনসোলে `>>>` না আসা পর্যন্ত কয়েক সেকেন্ড অপেক্ষা করুন।
3. প্রজেক্ট ফোল্ডারে নতুন টার্মিনাল খুলে চালান:
   ```bash
   mpremote connect port:rfc2217://localhost:4000 run src/main.py
   ```
   `(.venv)` সক্রিয় না থাকলে কমান্ডের শুরুতে `pipenv run` বসান।
4. LED জ্বলবে-নিভবে। থামাতে টার্মিনালে `Ctrl + C` চাপুন।

`run` কমান্ড কোড সেভ না করে সরাসরি চালায়, তাই রিসেট নিয়ে ঝামেলা নেই। কোড বদলালে `Ctrl + C` চেপে ৩ নম্বর ধাপ আবার চালান।

### বিকল্প: সিমুলেটরের বোর্ডে কোড সেভ করা

```bash
mpremote connect port:rfc2217://localhost:4000 fs cp src/main.py :main.py
```

তারপর সিমুলেটর কনসোলে ক্লিক করে শুধু `Ctrl + D` চাপুন। Stop বা Start **চাপবেন না**।

> ⚠️ আপলোডের পর সিমুলেশন Stop বা Start করলে সিমুলেটরের ফ্ল্যাশ নতুন হয়ে যায় (*Performing initial setup* দেখা যায়) এবং সেভ করা `main.py` মুছে যায়। এজন্য সাধারণত `run` কমান্ডই ভালো।

### সিমুলেটরের সমস্যা সমাধান

| সমস্যা | সমাধান |
|--------|--------|
| `could not enter raw repl` | সিমুলেটর এখনো বুট হচ্ছে। ১০ সেকেন্ড অপেক্ষা করে আবার চালান। |
| পোর্ট 4000 ব্যস্ত বা `failed to connect` | সিমুলেটর চালু আছে কি না দেখুন। অন্য প্রোগ্রাম পোর্ট ধরে থাকলে বন্ধ করুন। |
| `fs cp` এর সময় `OSError: [Errno 2] ENOENT` | স্বাভাবিক। `mpremote` ফাইল আছে কি না দেখছে। এরর নয়। |
| `Courtesy Notice` (pipenv) | শুধু সতর্কবার্তা। `(.venv)` সক্রিয় থাকলে `pipenv run` ছাড়াই `mpremote` চালান। |
| আপলোডের পর কনসোলে শুধু `>>>`, কিছু চলে না | সিমুলেশন রিস্টার্ট হয়ে ফাইল মুছে গেছে। `run` কমান্ড ব্যবহার করুন। |
| কোড চলছে কিন্তু LED জ্বলে না | তার যাচাই করুন: GPIO 2 → রেজিস্টর → LED anode, LED cathode → GND। |

## সমস্যা সমাধান

| সমস্যা | সমাধান |
|--------|--------|
| `could not enter raw repl` | বোর্ডে MicroPython ফ্ল্যাশ করা নেই। [MicroPython ফার্মওয়্যার ফ্ল্যাশ](#micropython-ফার্মওয়্যার-ফ্ল্যাশ) ধাপ করুন। |
| পোর্ট দেখা যায় না | চার্জ-অনলি ক্যাবল হতে পারে। ডেটা ক্যাবল ব্যবহার করুন। |
| ফ্ল্যাশে `Failed to connect` | কমান্ড চালানোর সময় **BOOT** বাটন চেপে ধরুন। `Connecting...` এলে ছেড়ে দিন। |
| LED জ্বলে না | LED অন্য পিনে থাকতে পারে। `Pin(2, ...)` এর নম্বর বদলে দেখুন। |
| `Device busy` | অন্য টার্মিনাল বা এক্সটেনশন পোর্ট ধরে রেখেছে। সেটা বন্ধ করুন। |
