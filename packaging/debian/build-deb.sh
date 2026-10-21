#!/usr/bin/env bash
# packaging/debian/build-deb.sh [output-dir]
set -euo pipefail

cd "$(dirname "$0")/../.."
VERSION="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" deepcool_lcd/__init__.py)"
OUT="$(realpath "${1:-dist}")"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

make install DESTDIR="$ROOT" PREFIX=/usr
install -d "$ROOT/usr/share/doc/deepcool-lcd"
install -m644 data/fonts/OFL-FiraSans.txt data/fonts/LICENSE-Hack.md "$ROOT/usr/share/doc/deepcool-lcd/"

install -d "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: deepcool-lcd
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-usb, python3-psutil, python3-pil (>= 9.1), systemd, udev
Recommends: python3-gi, gir1.2-gtk-4.0
Conflicts: deepcool-lm
Maintainer: zazazaxky-m <zazazaxky-m@users.noreply.github.com>
Homepage: https://github.com/zazazaxky-m/deepcool-lcd
Installed-Size: $(du -sk "$ROOT/usr" | cut -f1)
Description: Custom screens for DeepCool LM-series AIO cooler LCDs
 Shows live CPU and GPU temperatures, load, clocks, power and memory on the
 LCD of DeepCool LM-series AIO coolers, with 15 layouts, custom colors,
 adjustable brightness and refresh rate, pictures and solid colors.
 Includes DeepCool LCD Studio, a GTK 4 app to customize the screen.
 Not affiliated with DeepCool.
EOF

cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    systemd-sysusers /usr/lib/sysusers.d/deepcool-lcd.conf || true
    udevadm control --reload || true
    udevadm trigger --subsystem-match=usb --attr-match=idVendor=3633 --action=add || true
    udevadm trigger --subsystem-match=powercap --action=add || true
    systemctl daemon-reload || true
    systemctl disable --now deepcool-lm 2>/dev/null || true
    if [ -z "$2" ]; then
        systemctl enable --now deepcool-lcd || true
    elif systemctl is-active --quiet deepcool-lcd; then
        systemctl restart deepcool-lcd || true
    fi
fi
EOF

cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    systemctl disable --now deepcool-lcd || true
fi
EOF

cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    systemctl daemon-reload || true
    udevadm control --reload || true
fi
if [ "$1" = "purge" ]; then
    rm -rf /etc/deepcool-lcd
fi
EOF
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm" "$ROOT/DEBIAN/postrm"

mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT/deepcool-lcd_${VERSION}_all.deb"
