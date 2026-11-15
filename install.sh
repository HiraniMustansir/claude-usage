#!/usr/bin/env bash
# Installs the Claude Usage GNOME Shell extension for the current user.
set -euo pipefail

cd "$(dirname "$0")"
UUID="claude-usage@local"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
BIN_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons"

mkdir -p "$EXT_DIR" "$BIN_DIR" "$ICON_DIR"
cp "$UUID/metadata.json" "$UUID/extension.js" "$EXT_DIR/"
install -m 755 bin/claude-usage-widget.py "$BIN_DIR/claude-usage-widget.py"
cp icons/claude-usage-bot.svg icons/claude-usage.svg "$ICON_DIR/"

echo "Installed. Checking the helper script..."
python3 "$BIN_DIR/claude-usage-widget.py" --selftest

cat <<EOF

Next steps:
  1. Log out and log back in (Wayland can't restart GNOME Shell in place).
  2. Run:  gnome-extensions enable $UUID
EOF
