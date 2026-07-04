Name:           opentartarus
Version:        0.2.0
Release:        1%{?dist}
Summary:        Razer Tartarus Pro/V2 manager for Linux

License:        MIT
URL:            https://github.com/Moparmaniac412/OpenTartarus
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3 >= 3.8
Requires:       python3-pyqt6
Requires:       python3-evdev
Recommends:     openrazer-meta

%description
OpenTartarus is a Synapse-like tray application for the Razer
Tartarus Pro and Tartarus V2 keypads. It provides key remapping,
macro support, RGB lighting control via OpenRazer, and profile
management, running as a system tray app that launches on login.

%prep
%setup -q

%build
# Nothing to build - pure Python

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/opentartarus
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}/usr/lib/udev/rules.d

install -m 755 opentartarus.py %{buildroot}%{_datadir}/opentartarus/opentartarus.py

cat > %{buildroot}%{_bindir}/opentartarus << 'LAUNCHER'
#!/bin/bash
exec python3 %{_datadir}/opentartarus/opentartarus.py "$@"
LAUNCHER
chmod 755 %{buildroot}%{_bindir}/opentartarus

cat > %{buildroot}%{_datadir}/applications/opentartarus.desktop << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=OpenTartarus
Comment=Razer Tartarus Pro/V2 manager for Linux
Exec=/usr/bin/opentartarus
Icon=input-gaming
Categories=Settings;HardwareSettings;
Keywords=razer;tartarus;keypad;gaming;remap;
Terminal=false
DESKTOP

cat > %{buildroot}/usr/lib/udev/rules.d/99-opentartarus.rules << 'UDEV'
# OpenTartarus - Razer Tartarus Pro / V2
SUBSYSTEM=="input", ATTRS{idVendor}=="1532", ATTRS{idProduct}=="0244", MODE="0660", GROUP="input"
SUBSYSTEM=="input", ATTRS{idVendor}=="1532", ATTRS{idProduct}=="022b", MODE="0660", GROUP="input"
SUBSYSTEM=="input", ATTRS{idVendor}=="1532", ATTRS{idProduct}=="022c", MODE="0660", GROUP="input"
UDEV

%files
%{_bindir}/opentartarus
%{_datadir}/opentartarus/opentartarus.py
%{_datadir}/applications/opentartarus.desktop
/usr/lib/udev/rules.d/99-opentartarus.rules

%post
udevadm control --reload-rules >/dev/null 2>&1 || :
udevadm trigger >/dev/null 2>&1 || :
echo ""
echo "OpenTartarus installed."
echo ""
echo "IMPORTANT next steps:"
echo "  1. Add your user to the 'input' group:"
echo "       sudo usermod -aG input \$USER"
echo "  2. Log out and back in for group changes to take effect."
echo "  3. Launch OpenTartarus from your application menu, or run:"
echo "       opentartarus"
echo ""
echo "To launch automatically on login, open OpenTartarus and enable"
echo "'Launch on login' from the Settings tab."
echo ""

%postun
udevadm control --reload-rules >/dev/null 2>&1 || :

%changelog
* Fri Jul 04 2025 Moparmaniac412 <https://github.com/Moparmaniac412> - 0.2.0-1
- Add Tartarus V2 support
- Dynamic device detection by USB ID (survives reboots/replugs)
- Redesigned GUI
- Modifier key chaining, analog stick directional remapping
* Sun Jun 01 2025 Moparmaniac412 <https://github.com/Moparmaniac412> - 0.1.0-1
- Initial release
