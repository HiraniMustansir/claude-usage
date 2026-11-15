<p align="center">
  <img src="icons/claude-usage-bot.svg" alt="Claude Usage bot icon" width="112">
</p>

<h1 align="center">Claude Usage — GNOME Shell extension</h1>

<p align="center">See your Claude plan usage in the GNOME top bar, so the 5-hour limit doesn't catch you by surprise halfway through a task.</p>

<p align="center">
  <img src="icons/claude-usage-bot.svg" alt="" width="18" align="absmiddle">&nbsp;<code>42% · 17%</code>
</p>

- **Top bar:** `<5-hour %> · <weekly %>` next to the pixel bot icon.
- **Click it** for details (`5-hour: 42% · resets in 2h 30m`, `Weekly: …`), plus **Refresh now** and **Open usage window**.
- **Usage window:** a small GTK window with a progress bar for each limit.
- Updates every 15 seconds from a shared cache, while calling the API at most once a minute. If it gets rate-limited, it backs off and keeps showing your last numbers.

> Unofficial community project. Not affiliated with or endorsed by Anthropic.

## Who it's for

People on a Claude Pro or Max plan who use **Claude Code** on a Linux desktop running **GNOME Shell**.

## Requirements

| What | Notes |
|---|---|
| GNOME Shell **45 or newer** | Built and tested on GNOME 50. 45–49 use the same extension API and should work. |
| **Claude Code**, signed in with your Claude account | The extension reads the login token that Claude Code saves locally. |
| `python3` with **PyGObject** and **GTK 3** | Usually already installed on GNOME desktops. |

### Install the Python dependencies (if missing)

```bash
# Fedora
sudo dnf install python3-gobject gtk3

# Ubuntu / Debian / Pop!_OS / Linux Mint (GNOME)
sudo apt install python3-gi gir1.2-gtk-3.0

# Arch / Manjaro / EndeavourOS
sudo pacman -S python-gobject gtk3

# openSUSE
sudo zypper install python3-gobject-Gtk
```

### Distro compatibility

Any distro that ships **GNOME Shell 45+** should work, for example:

- Fedora Workstation 39+
- Ubuntu 24.04 LTS and newer
- Debian 13 (trixie) with GNOME
- Arch, Manjaro, EndeavourOS (GNOME edition)
- openSUSE Tumbleweed (GNOME)

KDE Plasma, XFCE, Cinnamon and other desktops can't load GNOME Shell extensions. On those, you can still run the standalone usage window (see below).

## Setup

### 1. Sign in to Claude Code

If you haven't already, install Claude Code, run `claude` once and sign in. That creates `~/.claude/.credentials.json`, which this extension reads.

### 2. Install the extension

```bash
git clone https://github.com/HiraniMustansir/claude-usage.git
cd claude-usage
./install.sh
```

The script copies these files to your user folders (no `sudo` needed):

| File | Installed to |
|---|---|
| `claude-usage@local/` | `~/.local/share/gnome-shell/extensions/claude-usage@local/` |
| `bin/claude-usage-widget.py` | `~/.local/bin/claude-usage-widget.py` |
| `icons/*.svg` | `~/.local/share/icons/` |

It ends by running a quick self-test that should print `ok`.

### 3. Reload GNOME Shell

- **Wayland** (the default on most distros): log out and log back in.
- **X11:** press `Alt` + `F2`, type `r`, press `Enter`.

### 4. Enable it

```bash
gnome-extensions enable claude-usage@local
```

Or turn it on in the **Extensions** app. Your usage should show up in the top bar within a few seconds.

### Standalone window (any desktop)

```bash
python3 ~/.local/bin/claude-usage-widget.py
```

On Wayland, apps can't force themselves on top. To keep the window above others, right-click its title bar and choose **Always on Top**.

## How it works

There's no push or websocket for usage data, so the extension polls, carefully.

1. Every 15 s (and when you open the menu), the extension runs `claude-usage-widget.py --panel`.
2. The script checks a shared cache at `~/.cache/claude-usage/usage.json`. If the API was called less than 60 s ago, it uses the cached result with no network call.
3. Otherwise it reads Claude Code's access token from `~/.claude/.credentials.json` and calls `GET https://api.anthropic.com/api/oauth/usage`, the same endpoint Claude Code's `/usage` command uses.
4. On **HTTP 429** it backs off: it waits as long as the server's `Retry-After` header says, or else 2 min, then 4, 8, up to 15 min. Meanwhile it keeps showing your last known numbers.
5. It prints the top-bar text on line 1 and the menu items on the lines after it.

The top bar, the usage window and **Refresh now** all share the same cache, so opening everything at once doesn't multiply API calls. **Refresh now** skips the 60 s wait (but not a rate-limit backoff).

The token is sent only to `api.anthropic.com`. The cache stores only the usage numbers and timestamps, never the token.

Script modes:

| Command | What it does |
|---|---|
| `claude-usage-widget.py` | Opens the GTK usage window |
| `claude-usage-widget.py --panel` | Prints text for the top bar and menu |
| `claude-usage-widget.py --panel --force` | Same, but skips the 60 s cache wait |
| `claude-usage-widget.py --selftest` | Runs the built-in checks |

## Troubleshooting

| You see | Fix |
|---|---|
| `⚠ Token expired — open Claude Code once` | The login token expired. Open Claude Code once and it refreshes the token. |
| `Rate limited — retrying in …` in the menu | The API is throttling requests. The extension backs off by itself and keeps your last numbers, so just wait. If it happens often, raise `MIN_FETCH_SECONDS`. |
| `⚠ Could not run usage script` | Check that `python3` and PyGObject are installed, then run `python3 ~/.local/bin/claude-usage-widget.py --panel` to see the error. |
| Extension doesn't appear | Make sure you logged out and back in after installing, then check `gnome-extensions info claude-usage@local`. |

To see extension errors live:

```bash
journalctl -f -o cat /usr/bin/gnome-shell
```

## Configuration

Settings at the top of `bin/claude-usage-widget.py`:

| Setting | Default | What it does |
|---|---|---|
| `MIN_FETCH_SECONDS` | `60` | Minimum time between real API calls. Lowering it risks HTTP 429. |
| `FIRST_BACKOFF` / `MAX_BACKOFF` | `120` / `900` | Rate-limit backoff range, in seconds |
| `UI_REFRESH_SECONDS` | `15` | How often the usage window re-reads the cache |

`POLL_SECONDS` in `extension.js` is how often the top bar re-reads the cache. It's cheap and doesn't call the API.

Re-run `./install.sh` after editing.

## Uninstall

```bash
./uninstall.sh
```

Then log out and back in.

## Caveats

- The usage endpoint is not a documented public API and could change without notice.
- On Linux, Claude Code stores credentials in `~/.claude/.credentials.json`. If a future version moves them, the script needs updating.

## License

MIT. See [LICENSE](LICENSE).
