#!/usr/bin/env bash
# curl -fsSL https://raw.githubusercontent.com/zazazaxky-m/deepcool-lcd/main/install.sh | sudo bash
# sudo ./install.sh [--uninstall]
set -euo pipefail

REPO="https://github.com/zazazaxky-m/deepcool-lcd"
REF="${DEEPCOOL_LCD_REF:-main}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m==>\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run me as root, e.g.: sudo $0 $*"
command -v systemctl >/dev/null || die "DeepCool LCD needs systemd (its service and udev rules)."

install_dependencies() {
    if command -v pacman >/dev/null; then
        pacman -S --needed --noconfirm python python-pyusb python-psutil python-pillow python-gobject gtk4 make
    elif command -v apt-get >/dev/null; then
        apt-get update
        apt-get install -y python3 python3-usb python3-psutil python3-pil python3-gi gir1.2-gtk-4.0 make
    elif command -v dnf >/dev/null; then
        dnf install -y python3 python3-pyusb python3-psutil python3-pillow python3-gobject gtk4 make
    elif command -v zypper >/dev/null; then
        zypper --non-interactive install python3 python3-pyusb python3-psutil python3-Pillow python3-gobject \
            typelib-1_0-Gtk-4_0 make
    else
        warn "Unknown package manager. Please install: Python 3, pyusb, psutil, Pillow, PyGObject + GTK 4, make"
    fi
}

find_source() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
    if [ -n "$here" ] && [ -f "$here/Makefile" ] && [ -d "$here/deepcool_lcd" ]; then
        SRC="$here"
        return
    fi
    command -v curl >/dev/null || die "Please install curl first."
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    say "Downloading DeepCool LCD ($REF)"
    curl -fsSL "$REPO/archive/$REF.tar.gz" | tar -xz -C "$TMP" --strip-components=1
    SRC="$TMP"
}

stop_old_driver() {
    if systemctl is-active --quiet deepcool-lm 2>/dev/null || systemctl is-enabled --quiet deepcool-lm 2>/dev/null; then
        say "Stopping the old deepcool-lm service (your settings are carried over)"
        systemctl disable --now deepcool-lm || true
    fi
}

if [ "${1:-}" = "--uninstall" ]; then
    find_source
    make -C "$SRC" uninstall PREFIX=/usr/local
    exit 0
fi

say "Installing dependencies"
install_dependencies
find_source
stop_old_driver
say "Installing DeepCool LCD"
make -C "$SRC" install PREFIX=/usr/local
systemctl enable --now deepcool-lcd
say "Done! Open 'DeepCool LCD Studio' from your app menu, or run: deepcool-lcd status"
