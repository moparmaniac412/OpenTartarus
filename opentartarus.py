#!/usr/bin/env python3
"""
Tartarus Pro Manager
A Synapse-like tray application for the Razer Tartarus Pro.
Runs the remap daemon in the background and provides a GUI for configuration.
"""

import sys
import json
import os
import time
import threading
import selectors
import copy
from evdev import InputDevice, UInput, ecodes, categorize, KeyEvent

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox, QGridLayout,
    QSlider, QColorDialog, QTabWidget, QMessageBox, QInputDialog,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QObject, QEvent, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter

try:
    from openrazer.client import DeviceManager
    OPENRAZER_AVAILABLE = True
except ImportError:
    OPENRAZER_AVAILABLE = False

# ── Config paths ───────────────────────────────────────────────
CONFIG_FILE         = os.path.expanduser("~/.tartarus_profiles.json")
ACTIVE_PROFILE_FILE = os.path.expanduser("~/.tartarus_active_profile")
AUTOSTART_DIR       = os.path.expanduser("~/.config/autostart")
AUTOSTART_FILE      = os.path.join(AUTOSTART_DIR, "opentartarus.desktop")
INSTALL_PATH        = os.path.expanduser("~/.opentartarus/opentartarus.py")

# ── Razer Tartarus Pro USB identifiers ────────────────────────
TARTARUS_VENDOR_ID  = 0x1532
TARTARUS_PRODUCT_ID = 0x0244

# ── Key signatures used to identify each sub-device ──────────
# The Tartarus Pro exposes 3 evdev devices:
#   KEYS device   — has KEY_Q, KEY_W, KEY_SPACE etc (main keypad)
#   MOUSE device  — has BTN_MIDDLE, REL_WHEEL (scroll wheel)
#   ANALOG device — has KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT (stick)
#
# We identify them by their capabilities rather than path numbers
# so reboots and USB reconnects don't break anything.

def find_tartarus_devices():
    """
    Dynamically find the three Tartarus Pro evdev devices by USB ID
    and capability fingerprint. Returns (keys_path, mouse_path, analog_path)
    or raises RuntimeError if not found.
    """
    import evdev as _evdev
    candidates = []
    for path in _evdev.list_devices():
        try:
            dev = _evdev.InputDevice(path)
            info = dev.info
            if info.vendor == TARTARUS_VENDOR_ID and info.product == TARTARUS_PRODUCT_ID:
                candidates.append(dev)
            else:
                dev.close()
        except Exception:
            pass

    if not candidates:
        raise RuntimeError("Razer Tartarus Pro not found. Is it plugged in?")

    keys_dev   = None
    mouse_dev  = None
    analog_dev = None

    for dev in candidates:
        caps = dev.capabilities()
        keys = caps.get(ecodes.EV_KEY, [])
        rels = caps.get(ecodes.EV_REL, [])

        has_space    = ecodes.KEY_SPACE  in keys
        has_middle   = ecodes.BTN_MIDDLE in keys
        has_wheel    = ecodes.REL_WHEEL  in rels
        has_arrows   = ecodes.KEY_UP     in keys
        has_leftalt  = ecodes.KEY_LEFTALT in keys
        has_q        = ecodes.KEY_Q      in keys
        has_leds = bool(caps.get(ecodes.EV_LED, []))
        has_abs = bool(caps.get(ecodes.EV_ABS, []))

        if has_middle and has_wheel and not has_q:
            mouse_dev = dev
        elif has_space and has_q and has_abs and has_wheel:
            keys_dev = dev
        elif has_space and has_q and not has_abs:
            analog_dev = dev
        else:
            dev.close()

    missing = []
    if not keys_dev:   missing.append("keys")
    if not mouse_dev:  missing.append("mouse/scroll")
    if not analog_dev: missing.append("analog stick")

    if missing:
        # Fallback: assign remaining candidates in order
        remaining = [d for d in candidates if d not in (keys_dev, mouse_dev, analog_dev)]
        if not keys_dev and remaining:   keys_dev   = remaining.pop(0)
        if not mouse_dev and remaining:  mouse_dev  = remaining.pop(0)
        if not analog_dev and remaining: analog_dev = remaining.pop(0)

    return keys_dev, mouse_dev, analog_dev


# ── Key map: built dynamically after device detection ─────────
# Maps (device_path, keycode) -> tartarus key id
# Populated in DaemonThread.setup_devices()
TARTARUS_KEY_MAP = {}

# Static key->id mapping by device role (filled after detection)
KEYS_DEVICE_MAP = {
    "KEY_1":        "01", "KEY_2":        "02", "KEY_3":        "03",
    "KEY_4":        "04", "KEY_5":        "05", "KEY_TAB":      "06",
    "KEY_Q":        "07", "KEY_W":        "08", "KEY_E":        "09",
    "KEY_R":        "10", "KEY_CAPSLOCK": "11", "KEY_A":        "12",
    "KEY_S":        "13", "KEY_D":        "14", "KEY_F":        "15",
    "KEY_LEFTSHIFT":"16", "KEY_Z":        "17", "KEY_X":        "18",
    "KEY_C":        "19", "KEY_SPACE":    "20",
}
MOUSE_DEVICE_MAP = {
    "BTN_MIDDLE": "scroll",
}
ANALOG_DEVICE_MAP = {
    "KEY_LEFTALT": "btn",
    "KEY_UP":      "analog_up",
    "KEY_DOWN":    "analog_down",
    "KEY_LEFT":    "analog_left",
    "KEY_RIGHT":   "analog_right",
}

# ── Key name -> evdev code ─────────────────────────────────────
def key_name_to_code(name):
    name = name.strip().lower()
    mapping = {
        "ctrl": ecodes.KEY_LEFTCTRL, "shift": ecodes.KEY_LEFTSHIFT,
        "alt": ecodes.KEY_LEFTALT, "super": ecodes.KEY_LEFTMETA,
        "tab": ecodes.KEY_TAB, "space": ecodes.KEY_SPACE,
        "return": ecodes.KEY_ENTER, "enter": ecodes.KEY_ENTER,
        "backspace": ecodes.KEY_BACKSPACE, "delete": ecodes.KEY_DELETE,
        "escape": ecodes.KEY_ESC, "esc": ecodes.KEY_ESC,
        "up": ecodes.KEY_UP, "down": ecodes.KEY_DOWN,
        "left": ecodes.KEY_LEFT, "right": ecodes.KEY_RIGHT,
        "home": ecodes.KEY_HOME, "end": ecodes.KEY_END,
        "prior": ecodes.KEY_PAGEUP, "next": ecodes.KEY_PAGEDOWN,
        "pageup": ecodes.KEY_PAGEUP, "pagedown": ecodes.KEY_PAGEDOWN,
        "insert": ecodes.KEY_INSERT, "caps_lock": ecodes.KEY_CAPSLOCK,
        "num_lock": ecodes.KEY_NUMLOCK, "scroll_lock": ecodes.KEY_SCROLLLOCK,
        "f1": ecodes.KEY_F1,   "f2": ecodes.KEY_F2,   "f3": ecodes.KEY_F3,
        "f4": ecodes.KEY_F4,   "f5": ecodes.KEY_F5,   "f6": ecodes.KEY_F6,
        "f7": ecodes.KEY_F7,   "f8": ecodes.KEY_F8,   "f9": ecodes.KEY_F9,
        "f10": ecodes.KEY_F10, "f11": ecodes.KEY_F11, "f12": ecodes.KEY_F12,
        "1": ecodes.KEY_1, "2": ecodes.KEY_2, "3": ecodes.KEY_3,
        "4": ecodes.KEY_4, "5": ecodes.KEY_5, "6": ecodes.KEY_6,
        "7": ecodes.KEY_7, "8": ecodes.KEY_8, "9": ecodes.KEY_9, "0": ecodes.KEY_0,
        "a": ecodes.KEY_A, "b": ecodes.KEY_B, "c": ecodes.KEY_C,
        "d": ecodes.KEY_D, "e": ecodes.KEY_E, "f": ecodes.KEY_F,
        "g": ecodes.KEY_G, "h": ecodes.KEY_H, "i": ecodes.KEY_I,
        "j": ecodes.KEY_J, "k": ecodes.KEY_K, "l": ecodes.KEY_L,
        "m": ecodes.KEY_M, "n": ecodes.KEY_N, "o": ecodes.KEY_O,
        "p": ecodes.KEY_P, "q": ecodes.KEY_Q, "r": ecodes.KEY_R,
        "s": ecodes.KEY_S, "t": ecodes.KEY_T, "u": ecodes.KEY_U,
        "v": ecodes.KEY_V, "w": ecodes.KEY_W, "x": ecodes.KEY_X,
        "y": ecodes.KEY_Y, "z": ecodes.KEY_Z,
        "-": ecodes.KEY_MINUS, "=": ecodes.KEY_EQUAL,
        "[": ecodes.KEY_LEFTBRACE, "]": ecodes.KEY_RIGHTBRACE,
        ";": ecodes.KEY_SEMICOLON, "'": ecodes.KEY_APOSTROPHE,
        ",": ecodes.KEY_COMMA, ".": ecodes.KEY_DOT, "/": ecodes.KEY_SLASH,
        "`": ecodes.KEY_GRAVE, "\\": ecodes.KEY_BACKSLASH,
    }
    return mapping.get(name)

def parse_combo(combo_str):
    parts = [p.strip() for p in combo_str.lower().split("+")]
    codes = []
    for part in parts:
        code = key_name_to_code(part)
        if code is not None:
            codes.append(code)
    return codes

def load_profiles():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "Default": {"keys": {}, "lighting": {"effect": "spectrum", "color": "#00FF00", "brightness": 80}},
        "WoW":     {"keys": {}, "lighting": {"effect": "static",   "color": "#FF8800", "brightness": 80}},
        "Valheim": {"keys": {}, "lighting": {"effect": "wave",     "color": "#0088FF", "brightness": 80}},
    }

def save_profiles(profiles):
    with open(CONFIG_FILE, "w") as f:
        json.dump(profiles, f, indent=2)

def get_active_profile_name(profiles):
    if os.path.exists(ACTIVE_PROFILE_FILE):
        with open(ACTIVE_PROFILE_FILE) as f:
            name = f.read().strip()
            if name in profiles:
                return name
    return list(profiles.keys())[0]

def set_active_profile_name(name):
    with open(ACTIVE_PROFILE_FILE, "w") as f:
        f.write(name)


# ── Daemon thread ──────────────────────────────────────────────
class DaemonThread(QThread):
    status_changed = pyqtSignal(str)

    # Modifier keycodes that should be held rather than tapped
    MODIFIER_CODES = {
        ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
        ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
        ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
        ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA,
    }

    # Map modifier name -> evdev code
    MODIFIER_NAME_MAP = {
        "ctrl":  ecodes.KEY_LEFTCTRL,
        "shift": ecodes.KEY_LEFTSHIFT,
        "alt":   ecodes.KEY_LEFTALT,
        "super": ecodes.KEY_LEFTMETA,
    }

    def __init__(self):
        super().__init__()
        self.mapping = {}
        self.ui = None
        self.devices = []
        self.running = False
        self.sel = selectors.DefaultSelector()
        self.config_mtime = 0
        self.profiles = {}
        self.held_modifiers = set()  # tracks currently held modifier codes

    def setup_uinput(self):
        cap = {
            ecodes.EV_KEY: list(ecodes.keys.keys()) + [
                ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE
            ],
        }
        self.ui = UInput(cap, name="Tartarus Pro Manager")
        self.status_changed.emit("uinput ready")

    def setup_devices(self):
        global TARTARUS_KEY_MAP
        try:
            keys_dev, mouse_dev, analog_dev = find_tartarus_devices()
        except RuntimeError as e:
            self.status_changed.emit(str(e))
            return

        TARTARUS_KEY_MAP = {}

        if keys_dev:
            for keycode, tid in KEYS_DEVICE_MAP.items():
                TARTARUS_KEY_MAP[(keys_dev.path, keycode)] = tid
            self.status_changed.emit(f"Keys device: {keys_dev.path}")

        if mouse_dev:
            for keycode, tid in MOUSE_DEVICE_MAP.items():
                TARTARUS_KEY_MAP[(mouse_dev.path, keycode)] = tid
            self.status_changed.emit(f"Mouse device: {mouse_dev.path}")

        if analog_dev:
            for keycode, tid in ANALOG_DEVICE_MAP.items():
                TARTARUS_KEY_MAP[(analog_dev.path, keycode)] = tid
            self.status_changed.emit(f"Analog device: {analog_dev.path}")

        for dev in [keys_dev, mouse_dev, analog_dev]:
            if dev:
                try:
                    # Reopen fresh to avoid stale file descriptor
                    saved_path = dev.path
                    dev.close()
                    dev = InputDevice(saved_path)
                    dev.grab()
                    self.devices.append(dev)
                    self.sel.register(dev, selectors.EVENT_READ)
                    self.status_changed.emit(f"Grabbed {dev.path} ({dev.name})")
                except Exception as e:
                    self.status_changed.emit(f"Could not grab {dev.path}: {e}")

    def reload_mapping(self):
        try:
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime != self.config_mtime:
                self.profiles = load_profiles()
                active = get_active_profile_name(self.profiles)
                self.mapping = self.profiles[active].get("keys", {})
                self.config_mtime = mtime
                self.status_changed.emit(f"Profile '{active}' loaded — {len(self.mapping)} keys")
        except Exception as e:
            self.status_changed.emit(f"Config error: {e}")

    def is_modifier_key(self, assignment_key):
        """Check if an assignment resolves to a pure modifier."""
        parts = [p.strip().lower() for p in assignment_key.split("+")]
        return all(p in self.MODIFIER_NAME_MAP for p in parts)

    def press_combo(self, combo_str, extra_modifiers=None):
        """Press and release a combo, including any currently held modifiers."""
        codes = parse_combo(combo_str)
        if not codes:
            return
        # Include held modifiers that aren't already in the combo
        held = set(extra_modifiers or self.held_modifiers)
        extra = [c for c in held if c not in codes]
        all_codes = extra + codes
        for code in all_codes:
            self.ui.write(ecodes.EV_KEY, code, 1)
        self.ui.syn()
        for code in reversed(all_codes):
            self.ui.write(ecodes.EV_KEY, code, 0)
        self.ui.syn()
        # Re-press held modifiers so they stay down
        for code in held:
            self.ui.write(ecodes.EV_KEY, code, 1)
        self.ui.syn()

    def press_macro(self, macro_str):
        for combo in macro_str.strip().split():
            self.press_combo(combo)
            time.sleep(0.05)

    def handle_event(self, device, event):
        if event.type != ecodes.EV_KEY:
            return
        key_event = categorize(event)
        keycode = key_event.keycode
        if isinstance(keycode, list):
            keycode = keycode[0]

        tartarus_id = TARTARUS_KEY_MAP.get((device.path, keycode))

        # ── Resolve what this key is mapped to ──
        assignment = self.mapping.get(tartarus_id, {}) if tartarus_id else {}
        mapped_key = assignment.get("key", "").strip()
        mapped_macro = assignment.get("macro", "").strip()

        # Resolve the actual evdev code to emit (mapped or passthrough)
        if mapped_key:
            emit_codes = parse_combo(mapped_key)
        else:
            orig = getattr(ecodes, keycode, None)
            emit_codes = [orig] if orig is not None else []

        if not emit_codes:
            return

        # Check if this resolves to a modifier
        is_modifier = all(c in self.MODIFIER_CODES for c in emit_codes)

        # ── key_up ──
        if key_event.keystate == KeyEvent.key_up:
            for code in emit_codes:
                self.ui.write(ecodes.EV_KEY, code, 0)
                if code in self.held_modifiers:
                    self.held_modifiers.discard(code)
            self.ui.syn()
            return

        # ── key_hold ──
        if key_event.keystate == KeyEvent.key_hold:
            if is_modifier:
                # Modifiers just stay held, already sent on key_down
                return
            # For analog directions and regular held keys, send repeat
            held_extra = [c for c in self.held_modifiers if c not in emit_codes]
            for code in held_extra + emit_codes:
                self.ui.write(ecodes.EV_KEY, code, 2)
            self.ui.syn()
            return

        # ── key_down ──
        if mapped_macro:
            self.press_macro(mapped_macro)
            return

        if is_modifier:
            # Hold modifier down — don't release until key_up
            for code in emit_codes:
                self.held_modifiers.add(code)
                self.ui.write(ecodes.EV_KEY, code, 1)
            self.ui.syn()
        elif tartarus_id and tartarus_id.startswith("analog_"):
            # Analog: press down with held modifiers, hold/up handled above
            held_extra = [c for c in self.held_modifiers if c not in emit_codes]
            for code in held_extra + emit_codes:
                self.ui.write(ecodes.EV_KEY, code, 1)
            self.ui.syn()
        else:
            # Regular key: press with held modifiers, then release
            held_extra = [c for c in self.held_modifiers if c not in emit_codes]
            all_codes = held_extra + emit_codes
            for code in all_codes:
                self.ui.write(ecodes.EV_KEY, code, 1)
            self.ui.syn()
            for code in reversed(all_codes):
                self.ui.write(ecodes.EV_KEY, code, 0)
            self.ui.syn()
            # Re-press held modifiers so they stay down
            for code in self.held_modifiers:
                self.ui.write(ecodes.EV_KEY, code, 1)
            self.ui.syn()

    def run(self):
        self.running = True
        self.setup_uinput()
        self.setup_devices()
        self.reload_mapping()
        last_reload = time.time()
        while self.running:
            try:
                events = self.sel.select(timeout=1.0)
                for key, mask in events:
                    device = key.fileobj
                    try:
                        for event in device.read():
                            self.handle_event(device, event)
                    except Exception:
                        pass
                if time.time() - last_reload > 2.0:
                    self.reload_mapping()
                    last_reload = time.time()
            except Exception:
                time.sleep(0.1)
        self.cleanup()

    def stop(self):
        self.running = False

    def cleanup(self):
        for dev in self.devices:
            try:
                dev.ungrab()
                dev.close()
            except Exception:
                pass
        if self.ui:
            self.ui.close()
        self.sel.close()


# ── Tray icon helper ───────────────────────────────────────────
def make_tray_icon(color="#00FF00"):
    """Generate a simple colored circle as tray icon."""
    px = QPixmap(22, 22)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("#333333"))
    painter.drawEllipse(2, 2, 18, 18)
    painter.end()
    return QIcon(px)


# ── Key / Scroll / Analog buttons ─────────────────────────────
class KeyButton(QPushButton):
    def __init__(self, key_id, label, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.label = label
        self.assignment = ""
        self.setFixedSize(68, 52)
        self.setCheckable(True)
        self.update_display()

    def update_display(self):
        short = self.assignment[:8] + "…" if len(self.assignment) > 8 else self.assignment
        self.setText(f"{self.label}\n{short}" if short else self.label)
        self.setStyleSheet("""
            QPushButton { background:#2a2a2a; color:#aaa; border:1px solid #444; border-radius:8px; font-size:10px; padding:2px; }
            QPushButton:checked { background:#3a3060; color:#b09fff; border:1.5px solid #7F77DD; }
            QPushButton:hover { border-color:#7F77DD; }
        """)

class ScrollButton(QPushButton):
    def __init__(self, key_id, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.assignment = ""
        self.setFixedSize(68, 116)
        self.setCheckable(True)
        self.setText("↑\nScroll\n↓")
        self.setStyleSheet("""
            QPushButton { background:#2a2a2a; color:#aaa; border:1px solid #444; border-radius:34px; font-size:10px; }
            QPushButton:checked { background:#3a3060; color:#b09fff; border:1.5px solid #7F77DD; }
            QPushButton:hover { border-color:#7F77DD; }
        """)

class AnalogButton(QPushButton):
    def __init__(self, key_id, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.assignment = ""
        self.setFixedSize(68, 68)
        self.setCheckable(True)
        self.setText("○\nAnalog")
        self.setStyleSheet("""
            QPushButton { background:#2a2a2a; color:#aaa; border:1px solid #444; border-radius:34px; font-size:10px; }
            QPushButton:checked { background:#3a3060; color:#b09fff; border:1.5px solid #7F77DD; }
            QPushButton:hover { border-color:#7F77DD; }
        """)


# ── Key capture filter ─────────────────────────────────────────
class KeyCaptureFilter(QObject):
    def __init__(self, app_window):
        super().__init__()
        self.app = app_window

    def eventFilter(self, obj, event):
        if self.app.recording and event.type() == QEvent.Type.KeyPress:
            self.app.handle_recorded_key(event)
            return True
        return False


# ── Main window ────────────────────────────────────────────────
class TartarusWindow(QMainWindow):
    def __init__(self, daemon):
        super().__init__()
        self.daemon = daemon
        self.setWindowTitle("Tartarus Pro Manager")
        self.setMinimumSize(760, 640)
        self.profiles = load_profiles()
        self.current_profile = get_active_profile_name(self.profiles)
        self.selected_key = None
        self.recording = False
        self.color = QColor("#00FF00")
        self.tartarus_device = None
        self.all_key_buttons = {}
        self.pending_changes = {}
        self.init_openrazer()
        self.init_ui()
        self.load_profile_to_ui()
        self.key_filter = KeyCaptureFilter(self)
        QApplication.instance().installEventFilter(self.key_filter)

    def closeEvent(self, event):
        # Hide to tray instead of closing
        event.ignore()
        self.hide()

    def init_openrazer(self):
        if not OPENRAZER_AVAILABLE:
            return
        try:
            dm = DeviceManager()
            for device in dm.devices:
                if "Tartarus" in device.name:
                    self.tartarus_device = device
                    break
        except Exception as e:
            print(f"OpenRazer error: {e}")

    def handle_recorded_key(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.stop_recording()
            return
        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier: parts.append("ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:   parts.append("shift")
        if mods & Qt.KeyboardModifier.AltModifier:     parts.append("alt")
        if mods & Qt.KeyboardModifier.MetaModifier:    parts.append("super")
        special = {
            Qt.Key.Key_Return: "Return", Qt.Key.Key_Space: "space",
            Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backspace: "BackSpace",
            Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down", Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right", Qt.Key.Key_CapsLock: "caps_lock",
            Qt.Key.Key_NumLock: "num_lock", Qt.Key.Key_ScrollLock: "scroll_lock",
            Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "Prior",
            Qt.Key.Key_PageDown: "Next",
            Qt.Key.Key_F1:  "F1",  Qt.Key.Key_F2:  "F2",  Qt.Key.Key_F3:  "F3",
            Qt.Key.Key_F4:  "F4",  Qt.Key.Key_F5:  "F5",  Qt.Key.Key_F6:  "F6",
            Qt.Key.Key_F7:  "F7",  Qt.Key.Key_F8:  "F8",  Qt.Key.Key_F9:  "F9",
            Qt.Key.Key_F10: "F10", Qt.Key.Key_F11: "F11", Qt.Key.Key_F12: "F12",
            Qt.Key.Key_Shift: "shift", Qt.Key.Key_Control: "ctrl",
            Qt.Key.Key_Alt: "alt", Qt.Key.Key_Meta: "super",
        }
        if key in special:
            k = special[key]
            if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control,
                       Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                self.key_input.setText(k)
                self.stop_recording()
                return
            parts.append(k)
        else:
            text = event.text().lower()
            if text and text.isprintable():
                parts.append(text)
        if parts:
            self.key_input.setText("+".join(parts))
            self.stop_recording()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.setStyleSheet("""
            QMainWindow, QWidget { background:#1a1a1a; color:#ddd; }
            QTabWidget::pane { border:1px solid #333; border-radius:8px; }
            QTabBar::tab { background:#2a2a2a; color:#888; padding:8px 20px; border-radius:4px; margin-right:4px; }
            QTabBar::tab:selected { background:#3a3060; color:#b09fff; }
            QGroupBox { border:1px solid #333; border-radius:8px; margin-top:8px; padding-top:8px; color:#888; font-size:11px; }
            QLineEdit { background:#2a2a2a; border:1px solid #444; border-radius:6px; padding:6px 10px; color:#ddd; }
            QLineEdit:focus { border-color:#7F77DD; }
            QComboBox { background:#2a2a2a; border:1px solid #444; border-radius:6px; padding:6px 10px; color:#ddd; }
            QPushButton#primary { background:#3a3060; color:#b09fff; border:1px solid #7F77DD; border-radius:6px; padding:8px 16px; }
            QPushButton#primary:hover { background:#4a40a0; }
            QPushButton#saveall { background:#1a3a1a; color:#80ff80; border:1px solid #44aa44; border-radius:6px; padding:8px 16px; }
            QPushButton#saveall:hover { background:#2a4a2a; }
            QPushButton#danger { background:#3a1a1a; color:#ff8080; border:1px solid #aa4444; border-radius:6px; padding:8px 16px; }
            QPushButton#record { background:#2a2a2a; color:#aaa; border:1px solid #444; border-radius:6px; padding:6px 12px; }
            QPushButton#record:checked { background:#3a1a1a; color:#ff6060; border-color:#aa3333; }
            QSlider::groove:horizontal { height:4px; background:#333; border-radius:2px; }
            QSlider::handle:horizontal { width:16px; height:16px; background:#7F77DD; border-radius:8px; margin:-6px 0; }
            QSlider::sub-page:horizontal { background:#7F77DD; border-radius:2px; }
        """)

        # Profile bar
        pbar = QHBoxLayout()
        pl = QLabel("Profile:"); pl.setStyleSheet("color:#888;font-size:13px;")
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profiles.keys())
        self.profile_combo.setCurrentText(self.current_profile)
        self.profile_combo.currentTextChanged.connect(self.on_profile_change)
        self.profile_combo.setFixedWidth(200)
        bn = QPushButton("+ New");   bn.setObjectName("primary"); bn.clicked.connect(self.new_profile)
        bc = QPushButton("Clone");   bc.setObjectName("primary"); bc.clicked.connect(self.clone_profile)
        bd = QPushButton("Delete");  bd.setObjectName("danger");  bd.clicked.connect(self.delete_profile)
        st = "🟢 Device connected" if self.tartarus_device else "🔴 No device"
        self.status_label = QLabel(st); self.status_label.setStyleSheet("color:#666;font-size:12px;")
        for w in [pl, self.profile_combo, bn, bc, bd]: pbar.addWidget(w)
        pbar.addStretch()
        pbar.addWidget(self.status_label)
        main_layout.addLayout(pbar)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # ── Remap tab ──
        rw = QWidget(); rl = QVBoxLayout(rw); rl.setSpacing(12)
        dg = QGroupBox("Keypad layout — click a key to remap it")
        dl = QHBoxLayout(dg); dl.setSpacing(8); dl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        def mk(kid, lbl):
            btn = KeyButton(kid, lbl)
            btn.clicked.connect(lambda _, k=kid: self.select_key(k))
            self.all_key_buttons[kid] = btn
            return btn

        c1 = QVBoxLayout(); c1.setSpacing(8); c1.setAlignment(Qt.AlignmentFlag.AlignTop); c1.addSpacing(62)
        for kid,lbl in [("01","01"),("06","06"),("11","11"),("16","16")]: c1.addWidget(mk(kid,lbl))
        dl.addLayout(c1)
        for ck in [[("02","02"),("07","07"),("12","12"),("17","17")],
                   [("03","03"),("08","08"),("13","13"),("18","18")],
                   [("04","04"),("09","09"),("14","14"),("19","19")]]:
            c = QVBoxLayout(); c.setSpacing(8); c.setAlignment(Qt.AlignmentFlag.AlignTop)
            for kid,lbl in ck: c.addWidget(mk(kid,lbl))
            dl.addLayout(c)
        c5 = QVBoxLayout(); c5.setSpacing(8); c5.setAlignment(Qt.AlignmentFlag.AlignTop)
        for kid,lbl in [("05","05"),("10","10"),("15","15")]: c5.addWidget(mk(kid,lbl))
        sb = ScrollButton("scroll"); sb.clicked.connect(lambda: self.select_key("scroll"))
        self.all_key_buttons["scroll"] = sb; c5.addWidget(sb); dl.addLayout(c5)
        sc = QVBoxLayout(); sc.setSpacing(8); sc.setAlignment(Qt.AlignmentFlag.AlignTop); sc.addSpacing(180)
        sc.addWidget(mk("btn","Btn"))
        ab = AnalogButton("analog"); ab.clicked.connect(lambda: self.select_key("analog"))
        self.all_key_buttons["analog"] = ab; sc.addWidget(ab)
        sc.addWidget(mk("20","20")); dl.addLayout(sc)
        rl.addWidget(dg)

        # Assignment panel
        from PyQt6.QtWidgets import QStackedWidget
        self.assign_group = QGroupBox("Select a key to remap it")
        al = QVBoxLayout(self.assign_group)

        self.assign_stack = QStackedWidget()

        # ── Page 0: normal key panel ──
        normal_page = QWidget()
        npl = QVBoxLayout(normal_page)
        npl.setContentsMargins(0,0,0,0)
        r1 = QHBoxLayout()
        kl = QLabel("Key / combo:"); kl.setStyleSheet("color:#888;font-size:13px;")
        self.key_input = QLineEdit(); self.key_input.setPlaceholderText("e.g. ctrl+c, F5, shift+1")
        self.key_input.textChanged.connect(self.auto_stage)
        self.record_btn = QPushButton("⏺ Record"); self.record_btn.setObjectName("record")
        self.record_btn.setCheckable(True); self.record_btn.setFixedWidth(100)
        self.record_btn.clicked.connect(self.toggle_record)
        r1.addWidget(kl); r1.addWidget(self.key_input); r1.addWidget(self.record_btn)
        npl.addLayout(r1)
        self.record_hint = QLabel("Press Record then hit a key or combo on your keyboard")
        self.record_hint.setStyleSheet("color:#666;font-size:11px;"); npl.addWidget(self.record_hint)
        r2 = QHBoxLayout()
        ml = QLabel("Macro:"); ml.setStyleSheet("color:#888;font-size:13px;")
        self.macro_input = QLineEdit(); self.macro_input.setPlaceholderText("e.g. ctrl+a ctrl+c ctrl+v")
        self.macro_input.textChanged.connect(self.auto_stage)
        r2.addWidget(ml); r2.addWidget(self.macro_input); npl.addLayout(r2)
        self.assign_stack.addWidget(normal_page)  # index 0

        # ── Page 1: analog directions panel ──
        analog_page = QWidget()
        apl = QVBoxLayout(analog_page)
        apl.setContentsMargins(0,0,0,0)
        hint = QLabel("Assign each analog stick direction — leave blank to use default arrow keys")
        hint.setStyleSheet("color:#666;font-size:11px;"); apl.addWidget(hint)
        self.analog_inputs = {}
        dir_label = {"analog_up":"↑  Up","analog_down":"↓  Down","analog_left":"←  Left","analog_right":"→  Right"}
        for dir_id, dir_lbl in dir_label.items():
            row = QHBoxLayout()
            lbl = QLabel(dir_lbl); lbl.setStyleSheet("color:#888;font-size:13px;"); lbl.setFixedWidth(80)
            inp = QLineEdit(); inp.setPlaceholderText("e.g. w, a, s, d or ctrl+w")
            inp.textChanged.connect(lambda text, d=dir_id: self.auto_stage_analog(d, text))
            row.addWidget(lbl); row.addWidget(inp)
            apl.addLayout(row)
            self.analog_inputs[dir_id] = inp
        self.assign_stack.addWidget(analog_page)  # index 1

        al.addWidget(self.assign_stack)

        # Shared buttons row
        cb = QPushButton("Clear"); cb.setFixedWidth(80)
        cb.setStyleSheet("background:#2a2a2a;border:1px solid #444;border-radius:6px;padding:8px 12px;color:#888;")
        cb.clicked.connect(self.clear_assignment)
        self.save_all_btn = QPushButton("💾 Save all"); self.save_all_btn.setObjectName("saveall")
        self.save_all_btn.setFixedWidth(120); self.save_all_btn.clicked.connect(self.save_all)
        br = QHBoxLayout(); br.addWidget(cb); br.addStretch(); br.addWidget(self.save_all_btn)
        al.addLayout(br)
        self.pending_label = QLabel(""); self.pending_label.setStyleSheet("color:#aa8800;font-size:11px;")
        al.addWidget(self.pending_label)
        rl.addWidget(self.assign_group)
        tabs.addTab(rw, "Remap")

        # ── Lighting tab ──
        lw = QWidget(); ll = QVBoxLayout(lw); ll.setSpacing(12)
        eg = QGroupBox("Effect"); el = QGridLayout(eg); self.effect_buttons = {}
        efx = [("Static","static"),("Spectrum","spectrum"),("Breath","breath_single"),
               ("Breath random","breath_random"),("Reactive","reactive"),("Wave","wave"),
               ("Starlight","starlight_single"),("Starlight random","starlight_random"),
               ("Ripple","ripple"),("None","none")]
        for i,(lbl,eff) in enumerate(efx):
            b = QPushButton(lbl); b.setCheckable(True)
            b.setStyleSheet("QPushButton{background:#2a2a2a;color:#888;border:1px solid #444;border-radius:6px;padding:8px;} QPushButton:checked{background:#3a3060;color:#b09fff;border:1.5px solid #7F77DD;} QPushButton:hover{border-color:#7F77DD;}")
            b.clicked.connect(lambda _,e=eff: self.select_effect(e))
            el.addWidget(b, i//5, i%5); self.effect_buttons[eff] = b
        ll.addWidget(eg)
        cg = QGroupBox("Color"); cl = QHBoxLayout(cg)
        for hc in ["#00FF00","#FF0000","#0088FF","#FF00FF","#FF8800","#FFFFFF"]:
            sw = QPushButton(); sw.setFixedSize(28,28)
            sw.setStyleSheet(f"background:{hc};border-radius:14px;border:none;")
            sw.clicked.connect(lambda _,c=hc: self.set_color(c)); cl.addWidget(sw)
        self.color_preview = QPushButton(); self.color_preview.setFixedSize(36,36)
        self.color_preview.setStyleSheet("background:#00FF00;border-radius:18px;border:2px solid #555;")
        self.color_preview.clicked.connect(self.pick_color)
        self.color_hex = QLineEdit("#00FF00"); self.color_hex.setFixedWidth(100)
        self.color_hex.editingFinished.connect(self.hex_color_changed)
        cl.addWidget(self.color_preview); cl.addWidget(QLabel("Hex:")); cl.addWidget(self.color_hex); cl.addStretch()
        ll.addWidget(cg)
        bg = QGroupBox("Brightness"); bl = QHBoxLayout(bg)
        self.bright_slider = QSlider(Qt.Orientation.Horizontal); self.bright_slider.setRange(0,100); self.bright_slider.setValue(80)
        self.bright_label = QLabel("80%"); self.bright_label.setFixedWidth(40)
        self.bright_slider.valueChanged.connect(lambda v: self.bright_label.setText(f"{v}%"))
        bl.addWidget(self.bright_slider); bl.addWidget(self.bright_label); ll.addWidget(bg)
        apb = QPushButton("Apply lighting"); apb.setObjectName("primary"); apb.clicked.connect(self.apply_lighting)
        ll.addWidget(apb); ll.addStretch()
        tabs.addTab(lw, "Lighting")

        # ── Settings tab ──
        sw2 = QWidget(); sl2 = QVBoxLayout(sw2); sl2.setSpacing(12)
        sg = QGroupBox("Startup"); sgl = QVBoxLayout(sg)
        self.autostart_btn = QPushButton()
        self.autostart_btn.setObjectName("primary")
        self.autostart_btn.clicked.connect(self.toggle_autostart)
        self.update_autostart_btn()
        sgl.addWidget(self.autostart_btn)
        sgl.addWidget(QLabel("Enables/disables automatic launch on login via KDE autostart."))
        sl2.addWidget(sg)
        dg2 = QGroupBox("Daemon status"); dgl = QVBoxLayout(dg2)
        self.daemon_label = QLabel("🟢 Daemon running")
        self.daemon_label.setStyleSheet("color:#80ff80;font-size:13px;")
        dgl.addWidget(self.daemon_label)
        sl2.addWidget(dg2)
        sl2.addStretch()
        tabs.addTab(sw2, "Settings")

    # ── Auto stage ────────────────────────────────────────────────
    def auto_stage(self):
        if not self.selected_key:
            return
        self.pending_changes[self.selected_key] = {
            "key": self.key_input.text(),
            "macro": self.macro_input.text(),
        }
        btn = self.all_key_buttons.get(self.selected_key)
        if btn and hasattr(btn, 'assignment'):
            btn.assignment = self.key_input.text() or self.macro_input.text()
            if hasattr(btn, 'update_display'):
                btn.update_display()
        self._update_pending_label()

    def auto_stage_analog(self, dir_id, text):
        self.pending_changes[dir_id] = {"key": text, "macro": ""}
        self._update_pending_label()

    def _update_pending_label(self):
        count = len(self.pending_changes)
        self.pending_label.setText(f"⏳ {count} unsaved change{'s' if count != 1 else ''} — click Save all when done")

    def select_key(self, key_id):
        for btn in self.all_key_buttons.values():
            btn.setChecked(False)
        self.all_key_buttons[key_id].setChecked(True)
        self.selected_key = key_id
        self.stop_recording()

        if key_id == "analog":
            # Show analog directions panel
            self.assign_stack.setCurrentIndex(1)
            self.assign_group.setTitle("Analog stick directions")
            keys = self.profiles[self.current_profile]["keys"]
            for dir_id, inp in self.analog_inputs.items():
                inp.blockSignals(True)
                staged = self.pending_changes.get(dir_id)
                if staged:
                    inp.setText(staged.get("key",""))
                else:
                    inp.setText(keys.get(dir_id, {}).get("key",""))
                inp.blockSignals(False)
        else:
            # Show normal key panel
            self.assign_stack.setCurrentIndex(0)
            self.key_input.blockSignals(True); self.macro_input.blockSignals(True)
            staged = self.pending_changes.get(key_id)
            if staged:
                self.key_input.setText(staged.get("key",""))
                self.macro_input.setText(staged.get("macro",""))
            else:
                saved = self.profiles[self.current_profile]["keys"].get(key_id, {})
                self.key_input.setText(saved.get("key",""))
                self.macro_input.setText(saved.get("macro",""))
            self.key_input.blockSignals(False); self.macro_input.blockSignals(False)
            self.assign_group.setTitle(f"Key {key_id}")

    def save_all(self):
        if not self.pending_changes:
            QMessageBox.information(self, "Nothing to save", "No pending changes.")
            return
        for kid, asgn in self.pending_changes.items():
            self.profiles[self.current_profile]["keys"][kid] = asgn
        save_profiles(self.profiles)
        count = len(self.pending_changes)
        self.pending_changes.clear()
        self.pending_label.setText("")
        QMessageBox.information(self, "Saved", f"Saved {count} assignment{'s' if count != 1 else ''} to '{self.current_profile}'!")

    def clear_assignment(self):
        if self.selected_key == "analog":
            for inp in self.analog_inputs.values():
                inp.clear()
        else:
            self.key_input.clear(); self.macro_input.clear()

    def toggle_record(self):
        if self.recording: self.stop_recording()
        else: self.start_recording()

    def start_recording(self):
        self.recording = True
        self.key_input.blockSignals(True); self.key_input.clear(); self.key_input.blockSignals(False)
        self.key_input.setPlaceholderText("Press a key or combo...")
        self.key_input.setStyleSheet("background:#3a1a1a;border:1px solid #aa3333;border-radius:6px;padding:6px 10px;color:#ff8080;")
        self.record_hint.setText("Listening… press Escape to cancel")
        self.record_btn.setChecked(True)

    def stop_recording(self):
        self.recording = False; self.record_btn.setChecked(False)
        self.key_input.setPlaceholderText("e.g. ctrl+c, F5, shift+1")
        self.key_input.setStyleSheet("")
        self.record_hint.setText("Press Record then hit a key or combo on your keyboard")

    def on_profile_change(self, name):
        self.pending_changes.clear(); self.pending_label.setText("")
        self.current_profile = name
        set_active_profile_name(name)
        self.load_profile_to_ui()

    def load_profile_to_ui(self):
        profile = self.profiles[self.current_profile]
        keys = profile.get("keys", {})
        for kid, btn in self.all_key_buttons.items():
            asgn = keys.get(kid, {})
            if hasattr(btn, 'assignment'):
                btn.assignment = asgn.get("key","") or asgn.get("macro","")
            if hasattr(btn, 'update_display'):
                btn.update_display()
        lighting = profile.get("lighting", {})
        for e, btn in self.effect_buttons.items():
            btn.setChecked(e == lighting.get("effect","spectrum"))
        self.set_color(lighting.get("color","#00FF00"))
        self.bright_slider.setValue(lighting.get("brightness", 80))

    def new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name and name not in self.profiles:
            self.profiles[name] = {"keys": {}, "lighting": {"effect": "spectrum", "color": "#00FF00", "brightness": 80}}
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name)
            save_profiles(self.profiles)

    def clone_profile(self):
        name, ok = QInputDialog.getText(self, "Clone Profile", "New profile name:")
        if ok and name and name not in self.profiles:
            self.profiles[name] = copy.deepcopy(self.profiles[self.current_profile])
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name)
            save_profiles(self.profiles)

    def delete_profile(self):
        if len(self.profiles) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete the last profile.")
            return
        del self.profiles[self.current_profile]
        self.profile_combo.removeItem(self.profile_combo.currentIndex())
        save_profiles(self.profiles)

    def select_effect(self, effect):
        for e, btn in self.effect_buttons.items(): btn.setChecked(e == effect)
        self.profiles[self.current_profile]["lighting"]["effect"] = effect
        save_profiles(self.profiles)

    def pick_color(self):
        color = QColorDialog.getColor(self.color, self)
        if color.isValid(): self.set_color(color.name())

    def hex_color_changed(self): self.set_color(self.color_hex.text())

    def set_color(self, hex_color):
        try:
            self.color = QColor(hex_color)
            self.color_preview.setStyleSheet(f"background:{hex_color};border-radius:18px;border:2px solid #555;")
            self.color_hex.setText(hex_color)
            self.profiles[self.current_profile]["lighting"]["color"] = hex_color
            save_profiles(self.profiles)
        except Exception: pass

    def apply_lighting(self):
        if not self.tartarus_device:
            QMessageBox.warning(self, "No device", "Tartarus Pro not connected via OpenRazer.")
            return
        lighting = self.profiles[self.current_profile].get("lighting", {})
        effect = lighting.get("effect", "spectrum")
        color = QColor(lighting.get("color", "#00FF00"))
        r, g, b = color.red(), color.green(), color.blue()
        try:
            self.tartarus_device.brightness = lighting.get("brightness", 80)
            fx = self.tartarus_device.fx
            if effect == "static":             fx.static(r, g, b)
            elif effect == "spectrum":         fx.spectrum()
            elif effect == "breath_single":    fx.breath_single(r, g, b)
            elif effect == "breath_random":    fx.breath_random()
            elif effect == "reactive":         fx.reactive(r, g, b, speed=1)
            elif effect == "wave":             fx.wave(1)
            elif effect == "starlight_single": fx.starlight_single(r, g, b, speed=1)
            elif effect == "starlight_random": fx.starlight_random(speed=1)
            elif effect == "ripple":           fx.ripple(r, g, b)
            elif effect == "none":             fx.none()
            QMessageBox.information(self, "Done", f"Applied {effect}!")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Autostart ─────────────────────────────────────────────────
    def is_autostart_enabled(self):
        return os.path.exists(AUTOSTART_FILE)

    def update_autostart_btn(self):
        if self.is_autostart_enabled():
            self.autostart_btn.setText("✅ Launch on login — click to disable")
        else:
            self.autostart_btn.setText("🚀 Enable launch on login")

    def toggle_autostart(self):
        if self.is_autostart_enabled():
            os.remove(AUTOSTART_FILE)
            QMessageBox.information(self, "Autostart", "Autostart disabled.")
        else:
            os.makedirs(AUTOSTART_DIR, exist_ok=True)
            script_path = os.path.abspath(sys.argv[0])
            desktop = f"""[Desktop Entry]
Type=Application
Name=Tartarus Pro Manager
Exec=bash -c 'sudo python3 {script_path}'
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            with open(AUTOSTART_FILE, "w") as f:
                f.write(desktop)
            QMessageBox.information(self, "Autostart", f"Will launch on login.\nScript: {script_path}")
        self.update_autostart_btn()


# ── Tray application ───────────────────────────────────────────
class TartarusApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle("Fusion")

        # Start daemon thread
        self.daemon = DaemonThread()
        self.daemon.status_changed.connect(self.on_daemon_status)
        self.daemon.start()

        # Main window
        self.window = TartarusWindow(self.daemon)

        # Tray icon
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(make_tray_icon("#00CC00"))
        self.tray.setToolTip("Tartarus Pro Manager")
        self.tray.activated.connect(self.on_tray_activated)

        menu = QMenu()
        open_action = menu.addAction("⚙️  Open Tartarus Manager")
        open_action.triggered.connect(self.show_window)
        menu.addSeparator()

        # Profile switcher submenu
        self.profile_menu = menu.addMenu("🎮 Switch profile")
        self.rebuild_profile_menu()
        menu.addSeparator()

        quit_action = menu.addAction("❌ Quit")
        quit_action.triggered.connect(self.quit)

        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.showMessage("Tartarus Pro Manager", "Running in the background.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def rebuild_profile_menu(self):
        self.profile_menu.clear()
        profiles = load_profiles()
        active = get_active_profile_name(profiles)
        for name in profiles.keys():
            action = self.profile_menu.addAction(f"{'✓ ' if name == active else '   '}{name}")
            action.triggered.connect(lambda _, n=name: self.switch_profile(n))

    def switch_profile(self, name):
        set_active_profile_name(name)
        self.window.profile_combo.setCurrentText(name)
        self.rebuild_profile_menu()
        self.tray.showMessage("Tartarus Pro Manager", f"Profile switched to '{name}'.", QSystemTrayIcon.MessageIcon.Information, 1500)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def on_daemon_status(self, msg):
        print(f"[daemon] {msg}")

    def quit(self):
        self.daemon.stop()
        self.daemon.wait(3000)
        self.tray.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    TartarusApp().run()
