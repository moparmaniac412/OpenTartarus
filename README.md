# OpenTartarus

A Synapse-like manager for the Razer Tartarus Pro on Linux. Runs as a system tray app, remaps keys, controls RGB lighting, and manages profiles — no Windows or Razer Synapse required.

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

---

## Requirements

- Linux (tested on Nobara/Fedora — should work on Ubuntu/Debian)
- Python 3.8+
- Razer Tartarus Pro (other Tartarus models may work)
- [OpenRazer](https://openrazer.github.io/) (installed automatically)

---

## Installation

```bash
git clone https://github.com/Moparmaniac412/OpenTartarus.git
cd OpenTartarus
./install.sh
```

Then **log out and back in** for device permissions to take effect.

After logging back in, OpenTartarus will start automatically and appear in your system tray as a green circle.

---

## Usage
I use this primarily for World Of Warcraft. I just wanted something that would work. I'm not a coder, I have a general IT knowledge. The coding was built primarily by ClaudeAI. If anyone sees this out there and has any improvements, that would be awesome. I feel like the Tartarus is one of those niche gaming devices that work well with MMORPGs. Thank you all <3
---

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

## Known Issues

Some `Ctrl+F` key combos may be intercepted by KDE before reaching your game (e.g. `Ctrl+F1`–`Ctrl+F4` switch virtual desktops). To fix, go to:

**System Settings → Shortcuts → KDE → KWin** and clear or reassign the conflicting shortcuts.

---

## Tested Hardware

| Device | Status |
|--------|--------|
| Razer Tartarus Pro | ✅ Fully working |
| Razer Tartarus V2 | ❓ Untested (likely works) |
| Razer Tartarus | ❓ Untested (likely works) |

---

## How It Works

OpenTartarus uses:
- **evdev** to intercept raw keypresses from the Tartarus devices
- **uinput** to emit remapped keypresses as a virtual keyboard
- **OpenRazer** for RGB lighting control
- **PyQt6** for the GUI and system tray

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

**Keys not remapping:**
Check group membership: `groups $USER` — should include `input` and `plugdev`.

**Modifier combos not working in some apps:**
Some KDE shortcuts intercept `Ctrl+F` keys at the compositor level. See Known Issues above.

---

## Contributing

Pull requests welcome! If you test on a Tartarus V2 or original Tartarus, please open an issue with your results.

---

## License

MIT — free to use, modify, and share.

---

*Built with ❤️ on Linux by [Moparmaniac412](https://github.com/Moparmaniac412)*
