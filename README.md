# Robotics Projects: MicroPython on ESP32

**English** | [বাংলা](README.bn.md)

A beginner-friendly workspace for learning robotics with **MicroPython** on the **ESP32**. You can run your code on a real board or on the Wokwi simulator inside VS Code, with no hardware needed.

## Quick Start

Already have MicroPython flashed on your ESP32? Get running in four steps. (First time? Do [Flash MicroPython Firmware](#flash-micropython-firmware) once.)

**1. Create the project**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pipenv
pipenv install
mkdir -p src
```

**2. Write the code.** Create `src/main.py`:

```python
from machine import Pin
from time import sleep

led = Pin(2, Pin.OUT)

while True:
    led.value(not led.value())  # toggle the LED
    sleep(0.5)
```

**3. Connect the device.** Plug in the ESP32 with a USB **data** cable, then find its port:

```bash
ls /dev/cu.*
PORT=/dev/cu.usbserial-XXXXXXXX   # use your port
```

**4. Run the code**

```bash
mpremote connect $PORT run src/main.py
```

The LED blinks. Press `Ctrl + C` to stop. To keep the program on the board so it runs at power-up, see [Run Programs](#run-programs). No board? Use the [simulator](#simulator-wokwi-in-vs-code).

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Setup](#setup)
5. [Working With a Real Device](#working-with-a-real-device)
6. [Flash MicroPython Firmware](#flash-micropython-firmware)
7. [Example: Blink an LED](#example-blink-an-led)
8. [Run Programs](#run-programs)
9. [VS Code Setup](#vs-code-setup)
10. [Simulator (Wokwi in VS Code)](#simulator-wokwi-in-vs-code)
11. [Troubleshooting](#troubleshooting)

## Prerequisites

| Item | Notes |
|------|-------|
| Python 3 | The `Pipfile` requests `3.15`. Adjust `python_version` if your installed version differs. |
| ESP32 board | Optional. The simulator works without one. |
| USB **data** cable | Charge-only cables will not work. |
| VS Code | Recommended, with the Python and Wokwi extensions. |

## Project Structure

```text
robotics/
├── Pipfile                # Python dependencies
├── Pipfile.lock
├── README.md              # English docs (this file)
├── README.bn.md           # Bangla docs
├── src/
│   └── main.py            # Your program
└── simulator/
    └── esp32/             # Wokwi config: wokwi.toml, diagram.json, firmware .bin
```

> `src/` and `simulator/` are not in the repository yet. Create them as you follow the steps below.

## Setup

### 1. Create a virtual environment

```bash
python3 -m venv .venv
```

### 2. Activate it

```bash
source .venv/bin/activate
```

### 3. Verify it is active

```bash
which python3
# Expected: <project path>/.venv/bin/python3
```

### 4. Install pipenv and the project dependencies

```bash
pip install pipenv
pipenv install
```

### 5. Install the packages (only if you are starting a new Pipfile)

```bash
pipenv install esptool mpremote
pipenv install --dev micropython-esp32-stubs
```

| Package | Purpose |
|---------|---------|
| `esptool` | Flash and inspect the ESP32 chip |
| `mpremote` | Run code on, and copy files to, a MicroPython board |
| `micropython-esp32-stubs` | Type stubs, so VS Code understands `machine` and similar modules |

## Working With a Real Device

### Find the serial port

Connect the ESP32 with a USB data cable, then run:

```bash
ls /dev/cu.*
```

Look for a name like `/dev/cu.usbserial-XXXXXXXX`. The examples below use `/dev/cu.usbserial-59450705951`. Replace it with your own port.

> Tip: store it in a variable once: `PORT=/dev/cu.usbserial-59450705951`, then use `$PORT` in the commands.

### Read board information

These `esptool` commands work **without** MicroPython installed:

| Goal | Command |
|------|---------|
| Chip type, features, crystal frequency, MAC | `esptool --port $PORT chip-id` |
| Flash memory size and type | `esptool --port $PORT flash-id` |
| MAC address | `esptool --port $PORT read-mac` |

These `mpremote` commands need MicroPython **already flashed**:

| Goal | Command |
|------|---------|
| List connected devices | `mpremote devs` |
| MicroPython version and board info | `mpremote connect $PORT exec "import os; print(os.uname())"` |
| List files on the board | `mpremote connect $PORT ls` |
| Free RAM and CPU frequency | `mpremote connect $PORT exec "import gc, machine; print('free RAM:', gc.mem_free()); print('CPU Hz:', machine.freq())"` |

## Flash MicroPython Firmware

You only need to do this once per board.

1. Download the latest stable `.bin` from <https://micropython.org/download/ESP32_GENERIC/>.
2. Erase the flash. **This deletes everything on the board.**
   ```bash
   esptool --port $PORT erase-flash
   ```
3. Write the firmware. Match the filename to what you downloaded.
   ```bash
   esptool --port $PORT --baud 460800 write-flash 0x1000 ~/Downloads/ESP32_GENERIC-*.bin
   ```
4. Test it:
   ```bash
   mpremote connect $PORT exec "print('hello')"
   ```
   If `hello` prints, the flash worked.

## Example: Blink an LED

Save this as `src/main.py`. It blinks an LED on **GPIO 2** every half second. GPIO 2 is also the built-in LED on most ESP32 dev boards.

```python
from machine import Pin
from time import sleep

led = Pin(2, Pin.OUT)  # GPIO 2 as an output

while True:
    led.value(1)   # LED on
    sleep(0.5)
    led.value(0)   # LED off
    sleep(0.5)
```

Wiring for an external LED: GPIO 2 → 220 Ω resistor → LED anode (long leg), LED cathode (short leg) → GND.

Run it with the commands in [Run Programs](#run-programs).

## Run Programs

Your program lives in `src/main.py`. To run a different file, replace `src/main.py` in the commands below with its path.

**Run once.** This does not save to the board. Press `Ctrl + C` to stop.

```bash
mpremote connect $PORT run src/main.py
```

**Save permanently.** The program runs on every power-up.

```bash
mpremote connect $PORT cp src/main.py :main.py
mpremote connect $PORT reset
```

**Turn the LED off** (GPIO 2):

```bash
mpremote connect $PORT exec "from machine import Pin; Pin(2, Pin.OUT).value(0)"
```

## VS Code Setup

To remove the `Import "machine" could not be resolved` warning, make sure `micropython-esp32-stubs` is installed. `pipenv install --dev` does this. Then:

1. Press `Cmd + Shift + P` and run **Python: Select Interpreter**.
2. Choose the `.venv` interpreter.
3. Run **Developer: Reload Window**.

## Simulator (Wokwi in VS Code)

You can run the ESP32 inside VS Code without a physical board. The simulator files are in `simulator/esp32/`: `wokwi.toml`, `diagram.json` and the MicroPython firmware. `diagram.json` wires an ESP32, an LED and a 220 Ω resistor to **GPIO 2**.

### Quick try in the browser

1. Go to <https://wokwi.com> and start a new **ESP32 → MicroPython** project.
2. Paste the code from `src/main.py` into `main.py` and press ▶.
3. Wire the LED to the pin labeled **2** on the right side (GPIO 2), through a 220 Ω resistor. Connect the other leg to GND.

> The **D2** label on the left side is actually GPIO 9. Do not use it.

### One-time setup in VS Code

1. Install the **Wokwi for VS Code** extension.
2. Press `F1` and run **Wokwi: Request a new License**. Get a free license in the browser and confirm it in VS Code.
3. Download the firmware if it is missing (it is not tracked in git):
   ```bash
   curl -L -o simulator/esp32/ESP32_GENERIC-20260824-v1.29.0.bin \
     https://github.com/wokwi/wokwi-vscode-micropython/raw/main/esp32/ESP32_GENERIC-20260824-v1.29.0.bin
   ```
   The firmware version (1.29.0) matches the `mpremote` version (1.29.0). `pipenv install --dev` keeps them in sync.

### Run each time (tested and working)

1. Open `simulator/esp32/diagram.json` in VS Code.
2. Click **▶ Start Simulation**, or press `F1` and run **Wokwi: Start Simulator**. Wait a few seconds until the console shows `>>>`.
3. Open a new terminal in the project folder and run:
   ```bash
   mpremote connect port:rfc2217://localhost:4000 run src/main.py
   ```
   If `(.venv)` is not active, prefix the command with `pipenv run`.
4. The LED blinks. Press `Ctrl + C` in the terminal to stop.

`run` executes the code directly without saving it, so there are no reset problems. After editing the code, press `Ctrl + C` and run step 3 again.

### Alternative: save the code to the simulated board

```bash
mpremote connect port:rfc2217://localhost:4000 fs cp src/main.py :main.py
```

Then click the simulator console and press `Ctrl + D`. Do **not** press Stop or Start.

> ⚠️ If you Stop or Start the simulation after uploading, the simulator's flash is reset (you will see *Performing initial setup*) and the saved `main.py` is deleted. This is why the `run` command is usually the better choice.

### Simulator troubleshooting

| Problem | Solution |
|---------|----------|
| `could not enter raw repl` | The simulator is still booting. Wait 10 seconds and try again. |
| Port 4000 busy, or `failed to connect` | Check that the simulator is running. Close any other program using the port. |
| `OSError: [Errno 2] ENOENT` during `fs cp` | Normal. `mpremote` is checking whether the file exists. It is not an error. |
| `Courtesy Notice` (pipenv) | A warning only. When `(.venv)` is active, run `mpremote` without `pipenv run`. |
| Only `>>>` after upload and nothing runs | The simulation restarted and deleted the file. Use the `run` command. |
| Code runs but the LED stays off | Check the wiring: GPIO 2 → resistor → LED anode, LED cathode → GND. |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `could not enter raw repl` | MicroPython is not flashed on the board. Do [Flash MicroPython Firmware](#flash-micropython-firmware). |
| Port not listed | You may have a charge-only cable. Use a data cable. |
| `Failed to connect` while flashing | Hold the **BOOT** button while running the command. Release it when `Connecting...` appears. |
| LED does not light | The LED may be on a different pin. Change the number in `Pin(2, ...)`. |
| `Device busy` | Another terminal or extension is holding the port. Close it. |
