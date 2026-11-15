import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const HOME = GLib.get_home_dir();
const SCRIPT = `${HOME}/.local/bin/claude-usage-widget.py`;
const ICON = `${HOME}/.local/share/icons/claude-usage-bot.svg`;
// How often the top bar re-reads usage. The script caches results and only calls the
// API at most once a minute (backing off on HTTP 429), so this tick is cheap.
const POLL_SECONDS = 15;

export default class ClaudeUsageExtension extends Extension {
    enable() {
        this._button = new PanelMenu.Button(0.0, 'Claude usage');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        box.add_child(new St.Icon({gicon: Gio.icon_new_for_string(ICON), style_class: 'system-status-icon'}));
        this._label = new St.Label({text: '…', y_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._label);
        this._button.add_child(box);

        this._details = new PopupMenu.PopupMenuSection();
        this._button.menu.addMenuItem(this._details);
        this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._button.menu.addAction('Refresh now', () => this._refresh(true));
        this._button.menu.addAction('Open usage window', () => GLib.spawn_async(null, ['python3', SCRIPT], null, GLib.SpawnFlags.SEARCH_PATH, null));

        this._button.menu.connect('open-state-changed', (_m, open) => { if (open) this._refresh(); });
        Main.panel.addToStatusArea(this.uuid, this._button);
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, POLL_SECONDS, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _refresh(force = false) {
        if (this._busy)
            return;
        this._busy = true;
        const argv = ['python3', SCRIPT, '--panel'];
        if (force)
            argv.push('--force');
        const proc = Gio.Subprocess.new(argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        proc.communicate_utf8_async(null, null, (p, res) => {
            this._busy = false;
            if (!this._button)
                return; // disabled while the script was running
            let lines = ['⚠', 'Could not run usage script'];
            try {
                const [, out] = p.communicate_utf8_finish(res);
                if (out.trim())
                    lines = out.trim().split('\n');
            } catch (e) {
                logError(e, 'claude-usage');
            }
            this._label.set_text(` ${lines[0]}`);
            this._details.removeAll();
            for (const line of lines.slice(1))
                this._details.addMenuItem(new PopupMenu.PopupMenuItem(line, {reactive: false}));
        });
    }

    disable() {
        GLib.source_remove(this._timer);
        this._timer = null;
        this._busy = false;
        this._button.destroy();
        this._button = this._label = this._details = null;
    }
}
