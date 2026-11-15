#!/usr/bin/env bash
# Removes the Claude Usage GNOME Shell extension for the current user.
set -euo pipefail

UUID="claude-usage@local"
gnome-extensions disable "$UUID" 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/$UUID"
rm -f "$HOME/.local/bin/claude-usage-widget.py"
rm -f "$HOME/.local/share/icons/claude-usage-bot.svg" "$HOME/.local/share/icons/claude-usage.svg"
echo "Uninstalled. Log out and back in to clear it from the top bar."
