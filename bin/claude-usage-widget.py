#!/usr/bin/env python3
"""Small always-on-top window showing Claude's 5-hour and weekly usage limits."""
import os, sys, json, threading, urllib.request, urllib.error
from datetime import datetime, timezone

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

CSS = b"""
window { background: #FAF9F5; color: #141413; }
.title { font-family: "Source Serif 4", Georgia, serif; font-size: 15pt; }
.name { font-weight: 600; }
.value, .status { color: #73726C; font-size: 90%; }
.card { background: #FFFFFF; border: 1px solid #E8E6DC; border-radius: 12px; padding: 10px 12px; }
progressbar trough { min-height: 8px; border-radius: 4px; background: #E8E6DC; border: none; }
progressbar progress { min-height: 8px; border-radius: 4px; background: #D97757; border: none; }
"""
ICON_DIR = os.path.expanduser("~/.local/share/icons")

CREDS = os.path.expanduser("~/.claude/.credentials.json")
URL = "https://api.anthropic.com/api/oauth/usage"  # same endpoint Claude Code's /usage reads
POLL_SECONDS = 15


def fetch():
    with open(CREDS) as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def describe(limit, now=None):
    """(fraction 0..1, label) for a block like {"utilization": 42.0, "resets_at": "...Z"}."""
    if not limit:
        return 0.0, "n/a"
    pct = float(limit.get("utilization") or 0)
    text = f"{pct:.0f}%"
    if limit.get("resets_at"):
        reset = datetime.fromisoformat(limit["resets_at"].replace("Z", "+00:00"))
        mins = max(0, int((reset - (now or datetime.now(timezone.utc))).total_seconds() // 60))
        d, h, m = mins // 1440, mins // 60 % 24, mins % 60
        text += " · resets in " + (f"{d}d {h}h" if d else f"{h}h {m}m")
    return min(pct / 100, 1.0), text


class Widget(Gtk.Window):
    def __init__(self):
        super().__init__(title="Claude usage")
        self.set_default_size(320, 230)
        self.set_keep_above(True)  # no-op on Wayland: use title bar right-click → Always on Top
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_icon_from_file(os.path.join(ICON_DIR, "claude-usage.svg"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        header = Gtk.Box(spacing=10)
        bot = GdkPixbuf.Pixbuf.new_from_file_at_size(os.path.join(ICON_DIR, "claude-usage-bot.svg"), 40, 40)
        header.pack_start(Gtk.Image.new_from_pixbuf(bot), False, False, 0)
        title = Gtk.Label(label="Claude usage", xalign=0)
        title.get_style_context().add_class("title")
        header.pack_start(title, False, False, 0)
        box.pack_start(header, False, False, 0)
        self.bars = {}
        for key, name in (("five_hour", "5-hour limit"), ("seven_day", "Weekly limit")):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.get_style_context().add_class("card")
            row = Gtk.Box(spacing=8)
            title, value = Gtk.Label(label=name, xalign=0), Gtk.Label(label="…", xalign=1)
            title.get_style_context().add_class("name")
            value.get_style_context().add_class("value")
            row.pack_start(title, False, False, 0)
            row.pack_end(value, False, False, 0)
            bar = Gtk.ProgressBar()
            card.pack_start(row, False, False, 0)
            card.pack_start(bar, False, False, 0)
            box.pack_start(card, False, False, 0)
            self.bars[key] = (bar, value)
        self.status = Gtk.Label(label="Loading…", xalign=0)
        self.status.get_style_context().add_class("status")
        box.pack_end(self.status, False, False, 0)
        self.add(box)
        self.connect("destroy", Gtk.main_quit)
        self.refresh()
        GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)

    def refresh(self):
        threading.Thread(target=self._worker, daemon=True).start()
        return True  # keep the timer running

    def _worker(self):
        try:
            data, err = fetch(), None
        except urllib.error.HTTPError as e:
            data, err = None, ("token expired — open Claude Code once" if e.code == 401 else e)
        except Exception as e:
            data, err = None, e
        GLib.idle_add(self._show, data, err)

    def _show(self, data, err):
        if err:
            self.status.set_text(f"Error: {err}")
            return False
        for key, (bar, value) in self.bars.items():
            frac, text = describe(data.get(key))
            bar.set_fraction(frac)
            value.set_text(text)
        self.status.set_text("Updated " + datetime.now().strftime("%H:%M:%S"))
        return False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert describe(None) == (0.0, "n/a")
        assert describe({"utilization": 42.0, "resets_at": "2026-01-01T02:30:00Z"}, now) == (0.42, "42% · resets in 2h 30m")
        assert describe({"utilization": 120, "resets_at": "2026-01-04T05:00:00+00:00"}, now) == (1.0, "120% · resets in 3d 5h")
        print("ok")
        sys.exit()
    if "--panel" in sys.argv:  # line 1 = top-bar text, other lines = menu details
        try:
            data = fetch()
        except urllib.error.HTTPError as e:
            sys.exit(print("⚠\n" + ("Token expired — open Claude Code once" if e.code == 401 else f"Error: {e}")))
        except Exception as e:
            sys.exit(print(f"⚠\nError: {e}"))
        pct = lambda k: f"{float((data.get(k) or {}).get('utilization') or 0):.0f}%"
        print(f"{pct('five_hour')} · {pct('seven_day')}")
        print("5-hour: " + describe(data.get("five_hour"))[1])
        print("Weekly: " + describe(data.get("seven_day"))[1])
        sys.exit()
    Widget().show_all()
    Gtk.main()
