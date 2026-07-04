# OpenTartarus

A Synapse-like manager for the Razer Tartarus Pro and Tartarus V2 on Linux. Runs as a system tray app, remaps keys, controls RGB lighting, and manages profiles — no Windows or Razer Synapse required.

![Platform](https://img.shields.io/badge/platform-Linux-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## Features

- 🎮 Full key remapping for all 20 keys + scroll wheel + extra button
- 🕹️ Analog stick directional remapping (Up/Down/Left/Right individually)
- ⌨️ Keystroke recording — press Record and hit any key or combo
- 🔀 Modifier key chaining — hold Shift or Ctrl and press another key for combos like `Shift+F1`
- 🔁 Macro support — chain multiple keypresses in sequence
- 💡 RGB lighting control (static, breathing, spectrum, wave, reactive, ripple, starlight)
- 👤 Multiple profiles with instant switching from the system tray
- 🚀 Launches automatically on login
- 🖥️ System tray app — runs silently in the background
- 🔌 Dynamic device detection — works reliably across reboots and USB replugs, no manual configuration needed

---

## Requirements

- Linux (tested on Nobara/Fedora — should work on Ubuntu/Debian)
- Python 3.8+
- Razer Tartarus Pro or Tartarus V2
- [OpenRazer](https://openrazer.github.io/) (installed automatically)

---

## Installation

### Option A — Packaged install (recommended)

Download the package for your distro from the [`packaging/`](packaging/) folder, then:

**Fedora / Nobara (.rpm):**
```bash
git clone https://github.com/moparmaniac412/OpenTartarus.git
cd OpenTartarus
sudo dnf install ./packaging/opentartarus-0.2.0-1.noarch.rpm
```

Then add yourself to the `input` group and log out/in:
```bash
sudo usermod -aG input $USER
```

Launch it from your application menu, or run `opentartarus` from a terminal.

### Option B — Install script (from source)

```bash
git clone https://github.com/moparmaniac412/OpenTartarus.git
cd OpenTartarus
chmod +x install.sh
./install.sh
```

Then **log out and back in** for device permissions to take effect.

After logging back in, OpenTartarus will start automatically and appear in your system tray as a green circle.

---

## Usage

### System tray
- **Left-click** the tray icon to open the manager
- **Right-click** for quick profile switching and quit

### Remapping keys
1. Click any key on the keypad layout
2. Type a key combo (e.g. `ctrl+c`, `F5`, `shift+1`) or click **⏺ Record** and press the key
3. For macros, enter space-separated combos in the Macro field (e.g. `ctrl+a ctrl+c ctrl+v`)
4. Changes stage automatically as you type
5. Click **💾 Save all** when done

### Analog stick
Click the **Analog** button to assign each direction (Up/Down/Left/Right) independently. Leave blank to use default arrow keys.

### Modifier combos (Shift, Ctrl, Alt)
Assign Shift or Ctrl to a key. When held, any other key pressed will fire as a combo — just like a real keyboard. For example: hold Shift (key 06) + press F1 (key 02) = `Shift+F1`.

### Lighting
1. Go to the **Lighting** tab
2. Choose an effect, color, and brightness
3. Click **Apply lighting**

### Profiles
- Create, clone, and delete profiles from the profile bar
- Switch instantly from the system tray right-click menu
- Each profile has its own key mappings and lighting settings

---

## Updating

If you pull a newer version from GitHub, make sure OpenTartarus is **fully quit** before replacing the file — closing the window only hides it to the tray, it doesn't stop the background daemon. If you overwrite the file while the old process is still running, your changes won't take effect until you actually restart it.

```bash
# Fully quit first: right-click tray icon → Quit
# or:
pkill -f opentartarus.py

# then replace the file and relaunch
cp opentartarus.py ~/.opentartarus/opentartarus.py
python3 ~/.opentartarus/opentartarus.py
```

If you installed via `.rpm`, update by reinstalling the new package instead:
```bash
sudo dnf install ./packaging/opentartarus-0.2.0-1.noarch.rpm
```

---

## Known Issues

Some `Ctrl+F` key combos may be intercepted by KDE before reaching your game (e.g. `Ctrl+F1`–`Ctrl+F4` switch virtual desktops). To fix, go to:

**System Settings → Shortcuts → KDE → KWin** and clear or reassign the conflicting shortcuts.

---

## Tested Hardware

| Device | Status |
|--------|--------|
| Razer Tartarus Pro | ✅ Fully working |
| Razer Tartarus V2 | ✅ Fully working |
| Razer Tartarus (original) | ❓ Untested (likely works) |

---

## How It Works

OpenTartarus uses:
- **evdev** to intercept raw keypresses from the Tartarus devices
- **uinput** to emit remapped keypresses as a virtual keyboard
- **OpenRazer** for RGB lighting control
- **PyQt6** for the GUI and system tray

Devices are detected dynamically by USB vendor/product ID and capability fingerprint (rather than hardcoded event paths), so the app keeps working correctly even after reboots or USB replugs shuffle the device numbering.

The remap daemon runs as a background thread inside the tray app. When a key is pressed, it looks up the mapping for the active profile and fires the correct keypress — including held modifiers for combos.

---

## Troubleshooting

**Tray icon doesn't appear after install:**
Log out and back in so group permissions (`input`, `plugdev`) take effect.

**"No device" shown in GUI:**
```bash
systemctl --user start openrazer-daemon
```
Then restart OpenTartarus.

**Keys not remapping, or remapping to the wrong thing:**
Make sure OpenTartarus is fully quit (not just window-closed) before restarting — see [Updating](#updating) above. Also check group membership: `groups $USER` should include `input` and `plugdev`.

**Modifier combos not working in some apps:**
Some KDE shortcuts intercept `Ctrl+F` keys at the compositor level. See Known Issues above.

**RPM install fails with a dependency error:**
Make sure your system has `python3-pyqt6` and `python3-evdev` available (Nobara/Fedora repos include these by default).

---

## Contributing

Pull requests welcome! If you test on the original (non-V2, non-Pro) Tartarus, please open an issue with your results.

---

## License

MIT — free to use, modify, and share.

---

*Built with ❤️ on Linux by [Moparmaniac412](https://github.com/Moparmaniac412) — with AI assistance from Claude (Anthropic).*
