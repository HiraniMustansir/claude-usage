#!/usr/bin/env python3
"""Shows Claude's 5-hour and weekly usage limits (GNOME top-bar helper + small GTK window).

All callers (the top-bar extension, the window, "Refresh now") share one cached result,
so the usage endpoint is hit at most once per MIN_FETCH_SECONDS no matter how many
things ask. On HTTP 429 it backs off (honouring Retry-After) and keeps showing the
last known numbers.
"""
import os, sys, json, time, fcntl, threading, urllib.request, urllib.error
from datetime import datetime, timezone

ICON_DIR = os.path.expanduser("~/.local/share/icons")
CREDS = os.path.expanduser("~/.claude/.credentials.json")
URL = "https://api.anthropic.com/api/oauth/usage"  # same endpoint Claude Code's /usage reads
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                     "claude-usage", "usage.json")

MIN_FETCH_SECONDS = 60     # real network calls at most this often (usage changes slowly)
FORCE_MIN_SECONDS = 10     # "Refresh now" can't spam faster than this
FIRST_BACKOFF = 120        # wait after the first 429 without Retry-After, doubles each time
MAX_BACKOFF = 15 * 60
UI_REFRESH_SECONDS = 15    # how often the window re-reads the cache (no network)


def fetch():
    with open(CREDS) as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def fmt_dur(secs):
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}s"
    m = secs // 60
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"


def _load():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(state):
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, CACHE)


def _note(s, now):
    if now < s.get("blocked_until", 0):
        return "Rate limited — retrying in " + fmt_dur(s["blocked_until"] - now)
    return s.get("error")


def get_usage(force=False, now=None, fetcher=None):
    """Return (data or None, fetched_at or None, note or None), using the shared cache."""
    now = time.time() if now is None else now
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # one process fetches; the rest read its result
        s = _load()
        since = now - s.get("attempted_at", 0)
        if now < s.get("blocked_until", 0) or since < (FORCE_MIN_SECONDS if force else MIN_FETCH_SECONDS):
            return s.get("data"), s.get("fetched_at"), _note(s, now)

        s["attempted_at"] = now
        s.pop("error", None)
        try:
            s["data"], s["fetched_at"], s["backoff"] = (fetcher or fetch)(), now, 0
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry = (e.headers or {}).get("Retry-After", "")
                s["backoff"] = int(retry) if retry.isdigit() else \
                    min(max(s.get("backoff", 0) * 2, FIRST_BACKOFF), MAX_BACKOFF)
                s["blocked_until"] = now + s["backoff"]
            elif e.code == 401:
                s["error"] = "Token expired — open Claude Code once"
            else:
                s["error"] = f"Error: {e}"
        except Exception as e:
            s["error"] = f"Error: {e}"
        _save(s)
        return s.get("data"), s.get("fetched_at"), _note(s, now)


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


def panel(force=False):
    """Line 1 = top-bar text, other lines = menu details."""
    data, fetched_at, note = get_usage(force)
    if not data:
        print("⚠\n" + (note or "No data yet"))
        return
    pct = lambda k: f"{float((data.get(k) or {}).get('utilization') or 0):.0f}%"
    print(f"{pct('five_hour')} · {pct('seven_day')}")
    print("5-hour: " + describe(data.get("five_hour"))[1])
    print("Weekly: " + describe(data.get("seven_day"))[1])
    print("Updated " + fmt_dur(time.time() - fetched_at) + " ago")
    if note:
        print(note)


CSS = b"""
window { background: #FAF9F5; color: #141413; }
.title { font-family: "Source Serif 4", Georgia, serif; font-size: 15pt; }
.name { font-weight: 600; }
.value, .status { color: #73726C; font-size: 90%; }
.card { background: #FFFFFF; border: 1px solid #E8E6DC; border-radius: 12px; padding: 10px 12px; }
progressbar trough { min-height: 8px; border-radius: 4px; background: #E8E6DC; border: none; }
progressbar progress { min-height: 8px; border-radius: 4px; background: #D97757; border: none; }
"""


def run_window():
    # GTK is only needed for the window, so the top-bar helper starts fast without it.
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

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
            GLib.timeout_add_seconds(UI_REFRESH_SECONDS, self.refresh)

        def refresh(self):
            threading.Thread(target=lambda: GLib.idle_add(self._show, *get_usage()), daemon=True).start()
            return True  # keep the timer running

        def _show(self, data, fetched_at, note):
            if data:
                for key, (bar, value) in self.bars.items():
                    frac, text = describe(data.get(key))
                    bar.set_fraction(frac)
                    value.set_text(text)
            status = ("Updated " + datetime.fromtimestamp(fetched_at).strftime("%H:%M:%S")) if fetched_at else ""
            self.status.set_text(" · ".join(x for x in (status, note) if x) or "Loading…")
            return False

    Widget().show_all()
    Gtk.main()


def selftest():
    import tempfile
    global CACHE
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert describe(None) == (0.0, "n/a")
    assert describe({"utilization": 42.0, "resets_at": "2026-01-01T02:30:00Z"}, now) == (0.42, "42% · resets in 2h 30m")
    assert describe({"utilization": 120, "resets_at": "2026-01-04T05:00:00+00:00"}, now) == (1.0, "120% · resets in 3d 5h")

    real_cache, calls = CACHE, []
    CACHE = os.path.join(tempfile.mkdtemp(), "usage.json")
    ok = lambda: calls.append(1) or {"five_hour": {"utilization": 10}}
    def limited(retry=""):
        def f():
            calls.append(1)
            raise urllib.error.HTTPError(URL, 429, "Too Many Requests", {"Retry-After": retry} if retry else {}, None)
        return f
    t = 1000.0
    assert get_usage(now=t, fetcher=ok)[0]["five_hour"]["utilization"] == 10 and len(calls) == 1
    assert get_usage(now=t + 30, fetcher=ok)[2] is None and len(calls) == 1          # cached, no call
    assert get_usage(now=t + 30, force=True, fetcher=ok) and len(calls) == 2         # forced refresh
    d, _, note = get_usage(now=t + 100, fetcher=limited())                            # 429 → keep old data
    assert d and note.startswith("Rate limited") and len(calls) == 3
    assert get_usage(now=t + 200, force=True, fetcher=ok)[2].startswith("Rate limited") and len(calls) == 3
    assert get_usage(now=t + 221, fetcher=limited())[2] and len(calls) == 4          # backoff doubled to 240s
    assert get_usage(now=t + 400, fetcher=ok) and len(calls) == 4
    assert get_usage(now=t + 462, fetcher=limited("30"))[2] == "Rate limited — retrying in 30s"  # Retry-After
    assert get_usage(now=t + 530, fetcher=ok)[2] is None and len(calls) == 6         # recovered
    CACHE = real_cache
    print("ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--panel" in sys.argv:
        panel(force="--force" in sys.argv)
    else:
        run_window()
