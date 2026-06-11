# MarvisAutoClick

**Auto-click "Confirm" dialogs so your AI agents don't stall while you're away.**
<img width="561" height="559" alt="image" src="https://github.com/user-attachments/assets/77276f5a-7a05-47e7-9810-ae921463424d" />


In the AI agent era, we set up automated pipelines, batch jobs, and AI workflows. They run great—until a modal pops up:

```
[Task Progress: ████████████░░░░ 67%]
"Are you sure?"
[    ✅ Confirm    ]
```

Everything pauses. Your agent waits. You're at lunch (or "working"). **This tool clicks that button for you.**

![Python](https://img.shields.io/badge/python-3.8+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How It Works

1. **📷 Capture a template** — Drag-select the "Confirm" button on your screen
2. **🔎 OpenCV matching** — Scans your screen in real-time for that exact pattern
3. **🖱️ Auto-clicks** — Clicks the center of the matched area when found
4. **🧊 Cooldown** — 8-second delay prevents repeat clicks
5. **⌨️ Global hotkey (F6)** — Toggle start/stop from any app, even games

---

## Quick Start

```bash
# Option 1: Download the exe from Releases → run it
# Option 2: Run from source
pip install pywin32 opencv-python numpy pillow
python auto_confirm.py
```

**⚠️ Run as Administrator if your target app also runs elevated.**

### Build your own .exe

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "MarvisAutoClick" auto_confirm.py
# Output: dist/MarvisAutoClick.exe
```

---

## Usage

| Step | Action |
|------|--------|
| 1 | Launch MarvisAutoClick |
| 2 | Click **📷 Capture Template** |
| 3 | On the full-screen overlay, **drag-select** the "Confirm" button |
| 4 | Press **F6** to start monitoring |
| 5 | Walk away — it clicks "Confirm" whenever it appears |

| Hotkey | Action |
|--------|--------|
| **F6** (default) | Toggle start / stop (global — works in any app) |
| Settings → Shortcut | Customize key + Ctrl/Alt/Shift |

---

## Features

- ✅ Works with **any on-screen button** — games, web apps, installers, custom UI
- ✅ **Global hotkey** — toggle from anywhere, even with the game focused
- ✅ **DirectInput compatible** — works where `mouse_event` fails
- ✅ **DPI aware** — handles high-DPI displays correctly
- ✅ **SendInput + mouse_event + SendMessage** — three click methods for max compatibility
- ✅ **Single-file Python** — easy to read, modify, and audit
- ✅ **~20MB standalone .exe** — no runtime dependencies

---

## Use Cases

| Scenario | Why |
|----------|-----|
| **AI agent pipelines** | Agent hits a confirm dialog while you're AFK |
| **Marvis automation** | Frequent confirmation popups break the flow |
| **Game grinding** | Click repetitive confirm dialogs while idle |
| **Batch installers** | Click through "Next → Confirm" on multiple installers |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| GUI | `tkinter` |
| Template matching | `OpenCV cv2.matchTemplate (TM_CCOEFF_NORMED)` |
| Screenshot | `PIL.ImageGrab` |
| Click simulation | `SendInput` (primary) + `mouse_event` + `SendMessage` |
| Global hotkey | `RegisterHotKey` + `PeekMessage` polling |
| Build | `PyInstaller —onefile` |

---

## License

MIT — free to use, modify, and distribute.
