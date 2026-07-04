# Packaging

Pre-built packages for OpenTartarus.

## Files

- `opentartarus-0.2.0-1.noarch.rpm` — Fedora/Nobara/RHEL package
- `opentartarus_0.2.0_all.deb` — Ubuntu/Debian package
- `opentartarus.spec` — RPM build recipe (rebuild it yourself on Fedora/Nobara for a guaranteed-native build)

## Installing

**Fedora / Nobara:**
```bash
sudo dnf install ./opentartarus-0.2.0-1.noarch.rpm
```

**Ubuntu / Debian:**
```bash
sudo apt install ./opentartarus_0.2.0_all.deb
```

After installing either package:
```bash
sudo usermod -aG input $USER
```
Then log out and back in.

## Rebuilding the RPM natively (recommended)

The `.rpm` in this folder was built in a generic sandbox. For a guaranteed-correct build on your own Fedora/Nobara system:

```bash
sudo dnf install rpm-build
mkdir -p ~/rpmbuild/SPECS ~/rpmbuild/SOURCES
cp opentartarus.spec ~/rpmbuild/SPECS/
mkdir opentartarus-0.2.0
cp ../opentartarus.py opentartarus-0.2.0/
tar czf ~/rpmbuild/SOURCES/opentartarus-0.2.0.tar.gz opentartarus-0.2.0/
rpmbuild -bb ~/rpmbuild/SPECS/opentartarus.spec
sudo dnf install ~/rpmbuild/RPMS/noarch/opentartarus-0.2.0-1*.rpm
```

## What the packages install

| Path | Purpose |
|------|---------|
| `/usr/bin/opentartarus` | Launcher script |
| `/usr/share/opentartarus/opentartarus.py` | Application code |
| `/usr/share/applications/opentartarus.desktop` | App menu entry |
| `/usr/lib/udev/rules.d/99-opentartarus.rules` | Device permission rules (Tartarus Pro + V2) |

Autostart-on-login is enabled from within the app itself (Settings tab), not by the package — since it's a per-user preference.
