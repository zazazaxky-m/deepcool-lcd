import base64
import sys
import threading
import time

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, PROJECT_URL, __version__  # noqa: E402
from .config import INTERVALS as INTERVAL_VALUES  # noqa: E402
from .ipc import ServiceNotRunning, image_command, request  # noqa: E402

APP_NAME = 'DeepCool LCD Studio'
PREVIEW_SCALE = 2
THUMB_SIZE = (186, 140)
SIDE_PANEL_WIDTH = 420
REFRESH_MS = 2000
THUMB_REFRESH_SECONDS = 30
INTERVALS = [(v, f'{v:g}s') for v in INTERVAL_VALUES]
APPLY_DELAY_MS = 300
MAX_IMAGE_BYTES = 50 * 1024 * 1024
NOT_RUNNING = "The deepcool-lcd service isn't running. Start it with: sudo systemctl enable --now deepcool-lcd"

MODE_LABELS = {'monitor': 'Showing system monitor', 'image': 'Showing an image', 'solid': 'Showing a solid color'}

ACCENT_PRESETS = ['#40c4ff', '#76e06f', '#b388ff', '#ff5c8a', '#ffb340', '#f5f7fa']
BACKGROUND_PRESETS = ['#090b10', '#000000', '#0e1726', '#171221', '#f2f4f8']

HIGHLIGHT = '#40c4ff'

CSS = """
.device {
  background-color: #040506;
  border-radius: 26px;
  padding: 14px;
  box-shadow: 0 18px 40px alpha(black, 0.38), inset 0 0 0 1px alpha(white, 0.07);
}
.lcd { border-radius: 10px; }

.app-title { font-weight: 700; }
.app-subtitle { font-size: 0.82em; opacity: 0.6; }

.section-title {
  font-size: 0.74em;
  font-weight: 700;
  letter-spacing: 0.09em;
  opacity: 0.5;
  margin: 0 6px 2px 6px;
}
.card {
  background-color: alpha(currentColor, 0.035);
  border: 1px solid alpha(currentColor, 0.08);
  border-radius: 14px;
}
.card-row { padding: 11px 16px; min-height: 32px; }
.card > .card-row:not(:last-child),
.card > revealer:not(:last-child) > .card-row { border-bottom: 1px solid alpha(currentColor, 0.06); }
.row-subtitle { font-size: 0.82em; opacity: 0.55; }

.segmented {
  background-color: alpha(currentColor, 0.07);
  border-radius: 9px;
  padding: 3px;
}
.segmented button {
  background: none;
  border: none;
  box-shadow: none;
  border-radius: 7px;
  padding: 3px 12px;
  min-height: 24px;
  min-width: 24px;
}
.segmented button:hover { background-color: alpha(currentColor, 0.06); }
.segmented button:checked { background-color: alpha(currentColor, 0.16); font-weight: 600; }

.theme-card {
  background: none;
  border: 2px solid transparent;
  border-radius: 14px;
  padding: 5px 5px 8px 5px;
  box-shadow: none;
}
.theme-card:hover { background-color: alpha(currentColor, 0.05); }
.theme-card:checked { border-color: %(hl)s; background-color: alpha(%(hl)s, 0.07); }
.theme-thumb { border-radius: 9px; }
.theme-name { font-size: 0.9em; opacity: 0.75; }
.theme-card:checked .theme-name { color: %(hl)s; opacity: 1; font-weight: 600; }

.swatch {
  min-width: 20px;
  min-height: 20px;
  padding: 0;
  border-radius: 999px;
  border: 2px solid alpha(currentColor, 0.18);
  box-shadow: none;
}
.swatch.selected { border-color: currentColor; box-shadow: 0 0 0 3px alpha(currentColor, 0.18); }
.custom-color button { padding: 2px; min-height: 22px; min-width: 22px; border-radius: 999px; }

.status-dot { font-size: 0.75em; color: #3fb950; }
.status-dot.offline { color: #e5484d; }
.status-error { color: #e5484d; }
.pill { border-radius: 999px; padding: 3px 14px; }
""" % {'hl': HIGHLIGHT}


def ipc_async(cmd, callback):
    def worker():
        try:
            response, error = request(cmd), None
        except (OSError, ValueError) as e:
            response, error = None, e

        def deliver():
            callback(response, error)
            return GLib.SOURCE_REMOVE
        GLib.idle_add(deliver)
    threading.Thread(target=worker, daemon=True).start()


def png_texture(b64):
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(base64.b64decode(b64)))


def hex_to_rgba(value):
    rgba = Gdk.RGBA()
    rgba.parse(value)
    return rgba


def rgba_to_hex(rgba):
    return '#%02x%02x%02x' % tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))


def swatch_css(colors):
    return ''.join(f'.swatch-{c[1:]} {{ background-color: {c}; }}\n' for c in colors)


def wheel_scrolls_page(widget, scroller):
    controller = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

    def on_scroll(ctl, _dx, dy):
        if widget.has_focus():
            return False
        adjustment = scroller.get_vadjustment()
        step = 1 if ctl.get_unit() == Gdk.ScrollUnit.SURFACE else 48
        adjustment.set_value(adjustment.get_value() + dy * step)
        return True

    controller.connect('scroll', on_scroll)
    widget.add_controller(controller)


def section(title, card):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    label = Gtk.Label(label=title.upper(), xalign=0)
    label.add_css_class('section-title')
    box.append(label)
    box.append(card)
    return box


class Card(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class('card')

    def add_row(self, title, control, subtitle=None):
        row = Gtk.Box(spacing=16)
        row.add_css_class('card-row')
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            sub.add_css_class('row-subtitle')
            text.append(sub)
        row.append(text)
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
        self.append(row)
        return row

    def add_revealed_row(self, title, control, subtitle=None):
        row = self.add_row(title, control, subtitle)
        self.remove(row)
        revealer = Gtk.Revealer(child=row, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.append(revealer)
        return revealer


class Segmented(Gtk.Box):
    def __init__(self, choices, on_change):
        super().__init__()
        self.add_css_class('segmented')
        self.buttons = {}
        self.on_change = on_change
        first = None
        for key, label in choices:
            button = Gtk.ToggleButton(label=label)
            if first:
                button.set_group(first)
            else:
                first = button
            button.connect('toggled', self._on_toggled, key)
            self.append(button)
            self.buttons[key] = button

    def _on_toggled(self, button, key):
        if button.get_active():
            self.on_change(key)

    def set_value(self, key):
        self.buttons[key].set_active(True)


class ColorPicker(Gtk.Box):
    def __init__(self, presets, on_change):
        super().__init__(spacing=7)
        self.on_change = on_change
        self.swatches = {}
        for color in presets:
            swatch = Gtk.Button(tooltip_text=color, valign=Gtk.Align.CENTER)
            swatch.add_css_class('swatch')
            swatch.add_css_class(f'swatch-{color[1:]}')
            swatch.connect('clicked', lambda _, c=color: self._pick(c))
            self.append(swatch)
            self.swatches[color] = swatch
        self.custom = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), tooltip_text='Custom color')
        self.custom.add_css_class('custom-color')
        self.custom.connect('notify::rgba', self._on_custom)
        self.append(self.custom)
        self.updating = False

    def _pick(self, color):
        self.set_value(color)
        self.on_change(color)

    def _on_custom(self, button, _pspec):
        if not self.updating:
            color = rgba_to_hex(button.get_rgba())
            self._mark(color)
            self.on_change(color)

    def _mark(self, color):
        for preset, swatch in self.swatches.items():
            if preset == color:
                swatch.add_css_class('selected')
            else:
                swatch.remove_css_class('selected')

    def set_value(self, color):
        self.updating = True
        self.custom.set_rgba(hex_to_rgba(color))
        self.updating = False
        self._mark(color)


class ThemeCard(Gtk.ToggleButton):
    def __init__(self, name):
        super().__init__()
        self.add_css_class('theme-card')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.thumb = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, overflow=Gtk.Overflow.HIDDEN)
        self.thumb.set_size_request(*THUMB_SIZE)
        self.thumb.add_css_class('theme-thumb')
        box.append(self.thumb)
        label = Gtk.Label(label=name)
        label.add_css_class('theme-name')
        box.append(label)
        self.set_child(box)


class StudioWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(1180, 760)
        self.config = None
        self.mode = 'monitor'
        self.connected = False
        self.loading = False  # true while filling in widgets
        self.pending = {}
        self.apply_source = None
        self.preview_busy = False
        self.preview_again = False
        self.thumb_queue = []
        self.thumb_running = False
        self.thumb_missing = set()
        self.last_thumbnails = 0.0
        self.refresh_source = None
        self.refresh_ms = None
        self.error_shown = False
        self.focus_themes = {'hero'}

        self.build_header()
        root = Gtk.Box(spacing=36, margin_top=28, margin_bottom=28, margin_start=32, margin_end=32)
        root.append(self.build_preview_column())
        root.append(self.build_side_panel())
        self.set_child(root)

        self.set_connected(False, 'Connecting to the deepcool-lcd service…')
        self.connect_service()
        self.set_refresh_interval(REFRESH_MS)


    def build_header(self):
        header = Gtk.HeaderBar()
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        title = Gtk.Label(label=APP_NAME)
        title.add_css_class('app-title')
        self.subtitle = Gtk.Label()
        self.subtitle.add_css_class('app-subtitle')
        titles.append(title)
        titles.append(self.subtitle)
        header.set_title_widget(titles)
        self.reset_button = Gtk.Button(label='Reset', tooltip_text='Restore the default look')
        self.reset_button.add_css_class('flat')
        self.reset_button.connect('clicked', self.on_reset)
        header.pack_end(self.reset_button)
        about = Gtk.Button(icon_name='help-about-symbolic', tooltip_text='About')
        about.add_css_class('flat')
        about.connect('clicked', self.on_about)
        header.pack_start(about)
        self.set_titlebar(header)

    def build_preview_column(self):
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, valign=Gtk.Align.START)

        device = Gtk.Box(halign=Gtk.Align.START)
        device.add_css_class('device')
        self.picture = Gtk.Picture(can_shrink=False, overflow=Gtk.Overflow.HIDDEN)
        self.picture.set_size_request(320 * PREVIEW_SCALE, 240 * PREVIEW_SCALE)
        self.picture.add_css_class('lcd')
        device.append(self.picture)
        column.append(device)

        status = Gtk.Box(spacing=8, margin_start=6, margin_end=6)
        self.status_dot = Gtk.Label(label='●')
        self.status_dot.add_css_class('status-dot')
        self.status = Gtk.Label(xalign=0, hexpand=True, wrap=True, max_width_chars=70)
        self.monitor_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE)
        back = Gtk.Button(label='Back to Monitor')
        back.add_css_class('pill')
        back.connect('clicked', lambda _: self.send_simple('monitor'))
        self.monitor_revealer.set_child(back)
        status.append(self.status_dot)
        status.append(self.status)
        status.append(self.monitor_revealer)
        column.append(status)
        return column

    def build_side_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, width_request=SIDE_PANEL_WIDTH)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.pages.add_titled(self.build_gallery_page(), 'layouts', 'Layouts')
        self.pages.add_titled(self.build_settings_page(), 'settings', 'Settings')
        top = Gtk.Box(spacing=12)
        switcher = Gtk.StackSwitcher(stack=self.pages)
        switcher.add_css_class('segmented')
        top.append(switcher)
        self.gallery_count = Gtk.Label(xalign=1, hexpand=True)
        self.gallery_count.add_css_class('app-subtitle')
        top.append(self.gallery_count)
        panel.append(top)
        panel.append(self.pages)
        return panel

    def build_gallery_page(self):
        self.gallery = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True, margin_end=12, margin_bottom=12)
        self.gallery_view = Gtk.Viewport(child=self.gallery)
        self.gallery_page = Gtk.ScrolledWindow(child=self.gallery_view, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.theme_cards = {}
        return self.gallery_page

    def build_gallery(self, themes, names):
        if self.theme_cards:
            return
        first = None
        for key in themes:
            card = ThemeCard(names.get(key, key.title()))
            if first:
                card.set_group(first)
            else:
                first = card
            card.connect('toggled', self.on_theme_toggled, key)
            index = len(self.theme_cards)
            self.gallery.attach(card, index % 2, index // 2, 1, 1)
            self.theme_cards[key] = card
        self.gallery_count.set_label(f'{len(themes)} designs')

    def build_settings_page(self):
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, margin_end=12, margin_bottom=12)
        scroller.set_child(self.controls)

        display = Card()
        self.focus_choice = Segmented([('cpu', 'CPU'), ('gpu', 'GPU')], lambda key: self.change(hero_focus=key))
        self.focus_revealer = display.add_revealed_row('Main reading', self.focus_choice, 'Big Number and Speedometer')
        self.unit_choice = Segmented([('C', '°C'), ('F', '°F')], lambda key: self.change(temp_unit=key))
        display.add_row('Temperature', self.unit_choice)
        self.clock_switch = Gtk.Switch()
        self.clock_switch.connect('notify::active', lambda sw, _: self.change(clock_24h=sw.get_active()))
        display.add_row('24-hour clock', self.clock_switch)
        self.label_entries = {}
        for key, title in (('cpu_label', 'CPU name'), ('gpu_label', 'GPU name')):
            entry = Gtk.Entry(max_length=24, width_chars=20)
            entry.connect('changed', self.on_label_changed, key)
            display.add_row(title, entry)
            self.label_entries[key] = entry
        self.controls.append(section('Display', display))

        colors = Card()
        self.color_pickers = {}
        for key, title, presets in (('cpu_color', 'CPU accent', ACCENT_PRESETS),
                                    ('gpu_color', 'GPU accent', ACCENT_PRESETS),
                                    ('background', 'Background', BACKGROUND_PRESETS)):
            picker = ColorPicker(presets, lambda color, k=key: self.change(**{k: color}))
            colors.add_row(title, picker)
            self.color_pickers[key] = picker
        self.controls.append(section('Colors', colors))

        lcd = Card()
        self.brightness = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 5)
        self.brightness.set_size_request(190, -1)
        self.brightness.set_draw_value(True)
        self.brightness.set_value_pos(Gtk.PositionType.RIGHT)
        self.brightness.set_format_value_func(lambda _scale, value: f'{value:.0f}%')
        self.brightness.connect('value-changed', lambda sc: self.change(brightness=int(round(sc.get_value()))))
        lcd.add_row('Brightness', self.brightness)
        self.interval_choice = Segmented(INTERVALS, self.on_interval_chosen)
        lcd.add_row('Refresh', self.interval_choice, 'Faster is smoother but uses a bit more CPU')
        image_button = Gtk.Button(label='Choose…')
        image_button.connect('clicked', self.on_choose_image)
        lcd.add_row('Image', image_button, 'Show a picture instead of stats')
        solid = Gtk.Box(spacing=8)
        self.solid_button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self.solid_button.add_css_class('custom-color')
        self.solid_button.set_rgba(hex_to_rgba('#000000'))
        show_solid = Gtk.Button(label='Show')
        show_solid.connect('clicked', self.on_show_solid)
        solid.append(self.solid_button)
        solid.append(show_solid)
        lcd.add_row('Solid color', solid, 'Black works as a screen-off')
        self.controls.append(section('LCD', lcd))
        wheel_scrolls_page(self.brightness, scroller)
        return scroller


    def set_connected(self, connected, message=None, error=False):
        self.connected = connected
        for widget in (self.controls, self.gallery_page, self.reset_button):
            widget.set_sensitive(connected)
        if connected:
            self.status_dot.remove_css_class('offline')
        else:
            self.status_dot.add_css_class('offline')
            self.subtitle.set_label('Not connected')
            self.monitor_revealer.set_reveal_child(False)
        if message is not None:
            self.set_status(message, error)

    def set_status(self, message, error=False):
        self.error_shown = error
        self.status.set_label(message)
        if error:
            self.status.add_css_class('status-error')
        else:
            self.status.remove_css_class('status-error')

    def connect_service(self, keep_status=False):
        ipc_async({'action': 'get_config'}, lambda r, e: self.on_config_loaded(r, e, keep_status))

    def on_config_loaded(self, response, error, keep_status=False):
        if error or response.get('status') != 'ok':
            if isinstance(error, ServiceNotRunning):
                message = NOT_RUNNING
            elif error:
                message = f"Can't reach the deepcool-lcd service: {error}"
            else:
                message = f"The deepcool-lcd service doesn't support this app version ({response.get('message')})."
            self.set_connected(False, message, error=True)
            return
        self.label_entries['cpu_label'].set_placeholder_text(f"Auto · {response['cpu_name']}")
        self.label_entries['gpu_label'].set_placeholder_text(f"Auto · {response['gpu_name']}")
        self.subtitle.set_label(f"{response['cpu_name']}  ·  {response['gpu_name']}")
        self.focus_themes = set(response.get('focus_themes', ['hero']))
        self.build_gallery(response['themes'], response.get('theme_names', {}))
        self.show_config(response['config'])
        self.set_connected(True)
        self.show_mode(response['mode'], update_status=not keep_status)
        self.request_preview()
        self.request_thumbnails()

    def show_config(self, config):
        self.config = config
        self.loading = True
        try:
            card = self.theme_cards.get(config['theme'])
            if card:
                card.set_active(True)
                GLib.idle_add(lambda: self.gallery_view.scroll_to(card, None) and False)
            self.focus_choice.set_value(config['hero_focus'])
            self.brightness.set_value(config.get('brightness', 100))
            self.interval_choice.set_value(config.get('interval', 2))
            self.set_refresh_interval(int(config.get('interval', 2) * 1000))
            for key, picker in self.color_pickers.items():
                picker.set_value(config[key])
            self.unit_choice.set_value(config['temp_unit'])
            self.clock_switch.set_active(config['clock_24h'])
            for key, entry in self.label_entries.items():
                if entry.get_text() != config[key]:
                    entry.set_text(config[key])
        finally:
            self.loading = False
        self.focus_revealer.set_reveal_child(config['theme'] in self.focus_themes)

    def show_mode(self, mode, update_status=True):
        self.mode = mode
        self.monitor_revealer.set_reveal_child(mode != 'monitor')
        if update_status:
            self.set_status(f"{MODE_LABELS.get(mode, mode)} · changes apply instantly")

    def set_refresh_interval(self, ms):
        if ms == self.refresh_ms:
            return
        if self.refresh_source:
            GLib.source_remove(self.refresh_source)
        self.refresh_ms = ms
        self.refresh_source = GLib.timeout_add(ms, self.on_tick)

    def on_interval_chosen(self, seconds):
        self.set_refresh_interval(int(seconds * 1000))
        self.change(interval=seconds)

    def on_tick(self):
        if self.connected:
            self.request_preview()
            if time.monotonic() - self.last_thumbnails >= THUMB_REFRESH_SECONDS:
                self.request_thumbnails()
            elif self.thumb_missing:
                self.request_thumbnails(sorted(self.thumb_missing))
        else:
            self.connect_service()
        return GLib.SOURCE_CONTINUE


    def change(self, **changes):
        if self.loading or not self.connected:
            return
        self.pending.update(changes)
        self.config.update(changes)
        if self.apply_source:
            GLib.source_remove(self.apply_source)
        self.apply_source = GLib.timeout_add(APPLY_DELAY_MS, self.apply_pending)

    def apply_pending(self):
        self.apply_source = None
        changes, self.pending = self.pending, {}
        if changes:
            ipc_async({'action': 'set_config', 'config': changes}, self.on_applied)
        return GLib.SOURCE_REMOVE

    def on_applied(self, response, error):
        if error:
            self.set_connected(False, f'Lost connection to the service: {error}', error=True)
            return
        if response.get('status') != 'ok':
            self.set_status(f"Couldn't apply: {response.get('message')}", error=True)
            self.connect_service(keep_status=True)
            return
        self.show_mode(response.get('mode', 'monitor'))
        self.request_preview()
        self.request_thumbnails()

    def on_theme_toggled(self, card, key):
        if card.get_active():
            self.focus_revealer.set_reveal_child(key in self.focus_themes)
            self.gallery_view.scroll_to(card, None)
            self.change(theme=key)

    def on_label_changed(self, entry, key):
        self.change(**{key: entry.get_text().strip()})

    def on_reset(self, _button):
        ipc_async({'action': 'reset_config'}, self.on_reset_done)

    def on_reset_done(self, response, error):
        if error or response.get('status') != 'ok':
            self.set_status(f"Couldn't reset: {error or response.get('message')}", error=True)
            return
        self.show_config(response['config'])
        self.show_mode(response.get('mode', 'monitor'))
        self.request_preview()
        self.request_thumbnails()

    def send_simple(self, action, **fields):
        ipc_async(dict(fields, action=action), self.on_simple_done)

    def on_simple_done(self, response, error):
        if error or response.get('status') != 'ok':
            self.set_status(f"Command failed: {error or response.get('message')}", error=True)
            return
        self.error_shown = False
        self.request_preview()

    def on_show_solid(self, _button):
        rgba = self.solid_button.get_rgba()
        self.send_simple('solid', color=[round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)])

    def on_choose_image(self, _button):
        images = Gtk.FileFilter(name='Images')
        images.add_mime_type('image/*')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog = Gtk.FileDialog(title='Choose an Image for the LCD', filters=filters)
        dialog.open(self, None, self.on_image_chosen)

    def on_image_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        try:
            _ok, data, _etag = file.load_contents(None)
        except GLib.Error as e:
            self.set_status(f"Couldn't read the image: {e.message}", error=True)
            return
        if len(data) > MAX_IMAGE_BYTES:
            self.set_status('That image is too large (max 50 MB).', error=True)
            return
        try:
            cmd = image_command(data)
        except (OSError, ValueError) as e:
            self.set_status(f"Couldn't open the image: {e}", error=True)
            return
        self.send_simple(cmd.pop('action'), **cmd)

    def on_about(self, _button):
        Gtk.AboutDialog(
            transient_for=self, modal=True, program_name=APP_NAME, version=__version__, logo_icon_name=APP_ID,
            comments='Custom screens for DeepCool LM-series AIO cooler LCDs.\nNot affiliated with DeepCool.',
            website=PROJECT_URL, license_type=Gtk.License.MIT_X11,
            authors=['zazazaxky-m', 'dlock (original deepcool-lm driver)']).present()


    def request_preview(self):
        if self.preview_busy:
            self.preview_again = True
            return
        self.preview_busy = True
        ipc_async({'action': 'frame', 'scale': PREVIEW_SCALE}, self.on_frame)

    def on_frame(self, response, error):
        self.preview_busy = False
        if error:
            self.set_connected(False, 'Lost the connection to the deepcool-lcd service. Retrying…', error=True)
            return
        if response.get('status') == 'ok':
            self.picture.set_paintable(png_texture(response['png']))
            if 'mode' in response:
                self.show_mode(response['mode'], update_status=not self.error_shown)
        if self.preview_again:
            self.preview_again = False
            self.request_preview()

    def request_thumbnails(self, keys=None):
        if keys is None:
            self.last_thumbnails = time.monotonic()
        for key in keys or self.theme_cards:
            if key not in self.thumb_queue:
                self.thumb_queue.append(key)
        self.next_thumbnail()

    def next_thumbnail(self):
        if self.thumb_running or not self.thumb_queue:
            return
        self.thumb_running = True
        key = self.thumb_queue.pop(0)
        ipc_async({'action': 'frame', 'config': {'theme': key}}, lambda r, e: self.on_thumbnail(key, r, e))

    def on_thumbnail(self, key, response, error):
        self.thumb_running = False
        if not error and response.get('status') == 'ok':
            self.theme_cards[key].thumb.set_paintable(png_texture(response['png']))
            self.thumb_missing.discard(key)
        else:
            self.thumb_missing.add(key)
        self.next_thumbnail()


class StudioApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS + swatch_css(set(ACCENT_PRESETS + BACKGROUND_PRESETS)))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or StudioWindow(self)
        window.present()


def main():
    GLib.set_application_name(APP_NAME)
    return StudioApp().run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
