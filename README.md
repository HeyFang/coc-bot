# 🐉 CoC-Bot

An open-source Clash of Clans farming bot built with Python and ADB. Automates multiplayer attacks using real-time screen capture and computer vision — no memory hacking, no game file modification.

Built and tested on **Linux (Arch/Manjaro)** with a physical Android device over USB.

---

## How It Works

```
Android Phone (CoC running)
        │
        │  USB-C → ADB
        ▼
   Screenshot capture
        │
        │  OpenCV template matching
        ▼
   Detect game state
        │
        │  Red zone edge detection
        ▼
   Deploy troops via ADB taps
```

The bot captures the screen via ADB, uses OpenCV template matching to identify UI elements, detects the deployable edge of the enemy base by scanning for the red no-deploy zone boundary, then sends randomized tap and swipe commands back through ADB.

---

## Features

- **Full attack automation** — navigates menus, finds match, deploys troops, waits for results, returns home, loops
- **Computer vision edge detection** — dynamically finds the deployable boundary on any enemy base, no hardcoded coordinates
- **Hero deployment + abilities** — deploys all three heroes and activates abilities mid-battle
- **Human behavior simulation** — randomized tap offsets, delays, swipe speeds, scroll amounts, idle behavior, and session lengths
- **Clustered troop deployment** — drops troops in a focused cluster with redundant taps so red zone misses don't waste troops
- **State machine architecture** — handles each game screen as a distinct state with fallback behavior

---

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.13 |
| Device bridge | ADB (Android Debug Bridge) |
| Screen capture | `adb exec-out screencap` |
| Image recognition | OpenCV (`cv2`) |
| Array processing | NumPy |
| Device | Physical Android phone (USB-C) |

---

## Requirements

- Linux (tested on Arch/Manjaro)
- Python 3.10+
- ADB (`sudo pacman -S android-tools` or `sudo apt install adb`)
- Android phone with USB debugging enabled
- Clash of Clans installed on the phone

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/HeyFang/coc-bot
cd coc-bot
```

**2. Create virtual environment and install dependencies**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Enable USB debugging on your phone**

`Settings → About Phone` → tap **Build Number** 7 times → `Settings → Developer Options` → enable **USB Debugging**.

**4. Connect your phone and verify ADB**
```bash
adb devices
```
Accept the USB debugging prompt on your phone and note the device ID shown.

**5. Configure your device ID**
```bash
cp .env.example .env
```
Edit `.env` and paste your device ID:
```
DEVICE_ID=your_device_id_here
```

**6. Generate templates**

With CoC open on your phone at the home village screen:
```bash
python crop_templates.py
```

---

## Usage

Make sure your phone is connected and CoC is open on the home village screen, then:

```bash
source venv/bin/activate
python bot.py
```

The bot will run a randomized number of attacks (8–12) within a randomized session window (1.5–3 hours) before stopping automatically.

---

## How the Attack Loop Works

```
[Home Village]
    ↓ tap Attack!
[Battle Menu]
    ↓ tap Find a Match
[Army Confirmation]
    ↓ tap Attack!
[Enemy Base loads]
    ↓ scroll to normalize view
    ↓ scan for red zone edge
    ↓ deploy dragons in cluster along edge
    ↓ deploy heroes
    ↓ wait ~30s → activate hero abilities
[Results screen]
    ↓ tap Return Home
[Home Village]
    ↓ idle behavior
    ↓ repeat
```

---

## Anti-Detection Measures

- All taps include random pixel offset (±15px)
- All delays are randomized ranges, never fixed values
- Swipe coordinates, speed, and distance vary each time
- Scroll normalization uses random repetition counts
- Idle behavior randomly chosen between pause, scroll, or extended pause
- Session length and attack count randomized each run
- Pre-tap reaction time simulates human response latency

---

## Limitations

- Requires a physical Android device — modern CoC detects and blocks emulators
- Templates need to be recropped after game UI updates
- Army must be pre-configured manually
- Attacks every base regardless of loot (threshold detection not yet implemented)

---

## TODO

- [x] **Loot detection** — read gold/elixir values via OCR and skip bases below threshold
- [ ] **Spell deployment** — auto-cast lightning/earthquake at optimal positions
- [ ] **Capital raid automation** — extend to handle clan capital raid weekends
- [ ] **Logging system** — track loot gained, attacks completed, win rate per session
- [ ] **Config file** — move thresholds, attack settings, session limits to `config.yaml`
- [ ] **GUI dashboard** — live bot status, stats, start/stop controls
- [ ] **True pinch-to-zoom** — multitouch zoom via `sendevent` for better base positioning
- [ ] **Multi-account support** — rotate between multiple devices

---

## Disclaimer

This project is built for educational purposes — to learn computer vision, ADB automation, and state machine design. Using bots in Clash of Clans violates Supercell's Terms of Service. Use at your own risk.

---

*Started as a curiosity about how CoC bots work. Built from scratch on Linux.*
