#!/bin/bash
# OpenTartarus Installer
# https://github.com/Moparmaniac412/OpenTartarus

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${YELLOW}  ██████╗ ██████╗ ███████╗███╗   ██╗${NC}"
echo -e "${YELLOW} ██╔═══██╗██╔══██╗██╔════╝████╗  ██║${NC}"
echo -e "${YELLOW} ██║   ██║██████╔╝█████╗  ██╔██╗ ██║${NC}"
echo -e "${YELLOW} ██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║${NC}"
echo -e "${YELLOW} ╚██████╔╝██║     ███████╗██║ ╚████║${NC}"
echo -e "${YELLOW}  ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝${NC}"
echo -e "${YELLOW}       T A R T A R U S${NC}"
echo ""
echo -e "${GREEN}OpenTartarus Installer${NC}"
echo "-----------------------------------------------"
echo ""

# Check not running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run this installer as root.${NC}"
    exit 1
fi

INSTALL_DIR="/home/$USER/.opentartarus"
AUTOSTART_DIR="/home/$USER/.config/autostart"
UDEV_RULE="/etc/udev/rules.d/99-opentartarus.rules"

echo "Installing to: $INSTALL_DIR"
echo ""

# ── Step 1: Dependencies ──────────────────────────────────────
echo -e "${YELLOW}[1/6] Installing dependencies...${NC}"

if command -v dnf &> /dev/null; then
    PKG="dnf"
    sudo dnf install -y python3 python3-pip --skip-unavailable 2>/dev/null || true
elif command -v apt &> /dev/null; then
    PKG="apt"
    sudo apt install -y python3 python3-pip python3-evdev 2>/dev/null || true
fi

pip install evdev PyQt6 --break-system-packages 2>/dev/null || \
pip install evdev PyQt6 --user 2>/dev/null || true

echo -e "${GREEN}  ✓ Dependencies installed${NC}"

# ── Step 2: OpenRazer ─────────────────────────────────────────
echo -e "${YELLOW}[2/6] Setting up OpenRazer...${NC}"

if ! python3 -c "from openrazer.client import DeviceManager" 2>/dev/null; then
    echo "  OpenRazer not found. Installing..."
    if [ "$PKG" = "dnf" ]; then
        sudo dnf config-manager addrepo --from-repofile=https://openrazer.github.io/hardware:razer.repo 2>/dev/null || true
        sudo dnf install -y openrazer-meta --skip-unavailable 2>/dev/null || true
    elif [ "$PKG" = "apt" ]; then
        sudo add-apt-repository ppa:openrazer/stable -y 2>/dev/null || true
        sudo apt update && sudo apt install -y openrazer-meta 2>/dev/null || true
    fi
    sudo gpasswd -a $USER plugdev
    echo -e "${GREEN}  ✓ OpenRazer installed${NC}"
else
    echo -e "${GREEN}  ✓ OpenRazer already installed${NC}"
fi

# ── Step 3: udev rule ─────────────────────────────────────────
echo -e "${YELLOW}[3/6] Setting up device permissions...${NC}"

sudo tee $UDEV_RULE > /dev/null << UDEV
# OpenTartarus - Razer Tartarus Pro
SUBSYSTEM=="input", ATTRS{idVendor}=="1532", ATTRS{idProduct}=="0244", MODE="0660", GROUP="input"
UDEV

sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG input $USER
echo -e "${GREEN}  ✓ udev rule created${NC}"

# ── Step 4: Install app ───────────────────────────────────────
echo -e "${YELLOW}[4/6] Installing OpenTartarus...${NC}"

mkdir -p "$INSTALL_DIR"
cp opentartarus.py "$INSTALL_DIR/opentartarus.py"
chmod +x "$INSTALL_DIR/opentartarus.py"

sudo tee /usr/local/bin/opentartarus > /dev/null << LAUNCHER
#!/bin/bash
python3 /home/$USER/.opentartarus/opentartarus.py "\$@"
LAUNCHER
sudo chmod +x /usr/local/bin/opentartarus

echo -e "${GREEN}  ✓ OpenTartarus installed to $INSTALL_DIR${NC}"

# ── Step 5: Autostart ─────────────────────────────────────────
echo -e "${YELLOW}[5/6] Setting up autostart...${NC}"

mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/opentartarus.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=OpenTartarus
Exec=python3 /home/$USER/.opentartarus/opentartarus.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-KDE-Autostart-enabled=true
DESKTOP

echo -e "${GREEN}  ✓ Autostart entry created${NC}"

# ── Step 6: Desktop entry ─────────────────────────────────────
echo -e "${YELLOW}[6/6] Creating application menu entry...${NC}"

mkdir -p "/home/$USER/.local/share/applications"
cat > "/home/$USER/.local/share/applications/opentartarus.desktop" << APPDESKTOP
[Desktop Entry]
Type=Application
Name=OpenTartarus
Comment=Razer Tartarus Pro Manager for Linux
Exec=python3 /home/$USER/.opentartarus/opentartarus.py
Icon=input-gaming
Categories=Settings;HardwareSettings;
Keywords=razer;tartarus;keyboard;gaming;
APPDESKTOP

echo -e "${GREEN}  ✓ App menu entry created${NC}"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "-----------------------------------------------"
echo -e "${GREEN}  OpenTartarus installed successfully!${NC}"
echo "-----------------------------------------------"
echo ""
echo "  Run it:       opentartarus"
echo "  App menu:     Settings > OpenTartarus"
echo ""
echo -e "${YELLOW}  IMPORTANT: Log out and back in for${NC}"
echo -e "${YELLOW}  device permissions to take effect.${NC}"
echo ""
