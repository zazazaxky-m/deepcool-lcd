import math
import os
import threading

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import paths
from .device import HEIGHT, WIDTH

SS = 3  # supersampling

FONT_FILES = {
    'Light': ('FiraSans-Light.ttf', 'DejaVuSans.ttf'),
    'Regular': ('FiraSans-Regular.ttf', 'DejaVuSans.ttf'),
    'Medium': ('FiraSans-Medium.ttf', 'DejaVuSans.ttf'),
    'SemiBold': ('FiraSans-SemiBold.ttf', 'DejaVuSans-Bold.ttf'),
    'Bold': ('FiraSans-Bold.ttf', 'DejaVuSans-Bold.ttf'),
    'Mono': ('Hack-Regular.ttf', 'DejaVuSansMono.ttf'),
}
SYSTEM_FONT_DIRS = (
    '/usr/share/fonts/TTF',                     # Arch
    '/usr/share/fonts/truetype/dejavu',         # Debian, Ubuntu
    '/usr/share/fonts/dejavu-sans-fonts',       # Fedora
    '/usr/share/fonts/dejavu-sans-mono-fonts',  # Fedora
    '/usr/share/fonts/dejavu',                  # openSUSE
    '/usr/share/fonts/truetype',
)

ICON_CPU, ICON_GPU, ICON_RAM = 'cpu', 'gpu', 'ram'
RAM_COLOR = (180, 140, 255)
TEMP_STOPS = [(30, (64, 196, 255)), (50, (80, 220, 150)), (68, (255, 210, 70)), (80, (255, 140, 50)), (90, (255, 64, 72))]

# FreeType isn't thread-safe
RENDER_LOCK = threading.Lock()
_font_cache = {}


def font_path(weight):
    bundled, fallback = FONT_FILES[weight]
    candidates = [os.path.join(paths.FONT_DIR, bundled)]
    candidates += [os.path.join(d, name) for name in (bundled, fallback) for d in SYSTEM_FONT_DIRS]
    return next((p for p in candidates if os.path.exists(p)), None)


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        path = font_path(weight)
        if path:
            _font_cache[key] = ImageFont.truetype(path, size * SS)
        else:
            try:
                _font_cache[key] = ImageFont.load_default(size * SS)
            except TypeError:  # Pillow < 10.1
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def hex_to_rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def mix(color, base, amount):
    return tuple(int(b + (c - b) * amount) for c, b in zip(color, base))


def clamp01(value):
    return max(0.0, min(value, 1.0))


def temp_color(temp):
    if temp <= TEMP_STOPS[0][0]:
        return TEMP_STOPS[0][1]
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        if temp <= t1:
            return mix(c1, c0, (temp - t0) / (t1 - t0))
    return TEMP_STOPS[-1][1]


def fmt_temp(celsius, config):
    value = celsius * 9 / 5 + 32 if config['temp_unit'] == 'F' else celsius
    return f"{value:.0f}°"


def fmt_clock(now, config):
    return now.strftime('%H:%M') if config['clock_24h'] else now.strftime('%I:%M').lstrip('0')


def fmt_uptime(seconds):
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return f"{days}d {hours}h" if days else f"{hours}:{minutes:02d}"


def fmt_date(now, short=False):
    return f"{now:%a}, {now.day} {now:%b}" if short else f"{now:%A}, {now.day} {now:%B}"


class Palette:
    def __init__(self, config):
        self.bg = hex_to_rgb(config['background'])
        self.cpu = hex_to_rgb(config['cpu_color'])
        self.gpu = hex_to_rgb(config['gpu_color'])
        r, g, b = self.bg
        self.dark = dark = 0.2126 * r + 0.7152 * g + 0.0722 * b < 140
        tint = (200, 215, 255) if dark else (20, 30, 50)
        self.card = mix(tint, self.bg, 0.055)
        self.border = mix(tint, self.bg, 0.11)
        self.track = mix(tint, self.bg, 0.17)
        self.text = (236, 240, 247) if dark else (22, 26, 34)
        self.muted = (128, 138, 158) if dark else (92, 100, 118)


class Canvas:
    def __init__(self, palette):
        self.pal = palette
        self.img = Image.new('RGB', (WIDTH * SS, HEIGHT * SS), palette.bg)
        self.d = ImageDraw.Draw(self.img)


    def text(self, xy, s, weight, size, fill, anchor='la'):
        self.d.text((xy[0] * SS, xy[1] * SS), s, font=font(weight, size), fill=fill, anchor=anchor)

    def text_width(self, s, weight, size):
        return self.d.textlength(s, font=font(weight, size)) / SS

    def fit_size(self, s, weight, size, max_width):
        while size > 8 and self.text_width(s, weight, size) > max_width:
            size -= 2
        return size


    @staticmethod
    def icon_width(icon, size):
        return size * 0.74 * {ICON_CPU: 1.0, ICON_GPU: 1.3, ICON_RAM: 1.35}[icon]

    def icon(self, icon, x, baseline, size, color):
        h = size * 0.74
        w = self.icon_width(icon, size)
        top, stroke = baseline - h, max(1.0, h * 0.13)
        if icon == ICON_CPU:
            pin = h * 0.17
            self.rect([x + pin, top + pin, x + w - pin, baseline - pin], h * 0.12, outline=color, width=stroke)
            self.rect([x + h * 0.38, top + h * 0.38, x + w - h * 0.38, baseline - h * 0.38], h * 0.04, fill=color)
            for i in range(3):
                p = top + pin + stroke + (h - 2 * pin - 2 * stroke) * (i + 0.5) / 3
                q = x + pin + stroke + (w - 2 * pin - 2 * stroke) * (i + 0.5) / 3
                for line in (((x, p), (x + pin, p)), ((x + w - pin, p), (x + w, p)),
                             ((q, top), (q, top + pin)), ((q, baseline - pin), (q, baseline))):
                    self.line(line, color, stroke * 0.8)
        elif icon == ICON_GPU:
            card_bottom = baseline - h * 0.2
            self.rect([x, top + h * 0.12, x + w, card_bottom], h * 0.12, outline=color, width=stroke)
            self.dot(x + w * 0.64, (top + h * 0.12 + card_bottom) / 2, h * 0.2, color)
            self.rect([x + w * 0.12, card_bottom, x + w * 0.62, baseline], 0, fill=color)
            self.rect([x + w * 0.12, top + h * 0.34, x + w * 0.36, top + h * 0.48], 0, fill=color)
        else:
            body_top, body_bottom = top + h * 0.2, baseline - h * 0.26
            self.rect([x, body_top, x + w, body_bottom], h * 0.08, outline=color, width=stroke)
            for i in range(3):
                cx = x + w * (0.2 + 0.3 * i)
                self.rect([cx - h * 0.1, body_top + h * 0.16, cx + h * 0.1, body_bottom - h * 0.16], 0, fill=color)
            for i in range(5):
                px = x + w * (0.12 + 0.19 * i)
                self.line([(px, body_bottom), (px, baseline)], color, stroke * 0.8)

    def labeled(self, xy, icon, s, weight, size, fill, icon_fill, anchor='ls'):
        x, y = xy
        icon_w = self.icon_width(icon, size) + size * 0.4
        if anchor == 'ms':
            x -= (icon_w + self.text_width(s, weight, size)) / 2
        self.icon(icon, x, y, size, icon_fill)
        self.text((x + icon_w, y), s, weight, size, fill, anchor='ls')


    def rect(self, box, radius, fill=None, outline=None, width=1):
        self.d.rounded_rectangle([v * SS for v in box], radius=radius * SS, fill=fill, outline=outline,
                                 width=max(1, round(width * SS)))

    def dot(self, x, y, r, color):
        self.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=color)

    def line(self, points, color, width=1.0):
        self.d.line([(x * SS, y * SS) for x, y in points], fill=color, width=max(1, int(width * SS)), joint='curve')

    def bar(self, x, y, w, h, frac, color):
        self.rect([x, y, x + w, y + h], h / 2, fill=self.pal.track)
        if frac > 0.005:
            self.rect([x, y, x + max(h, w * clamp01(frac)), y + h], h / 2, fill=color)

    def arc(self, cx, cy, r, width, start, sweep, color):
        if sweep <= 0:
            return
        color_at = color if callable(color) else (lambda f: color)
        box = [(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS]
        if callable(color):
            steps = max(2, int(sweep / 2))
            for i in range(steps):
                a0 = start + sweep * i / steps
                self.d.arc(box, a0, a0 + sweep / steps + 0.6, fill=color_at(i / steps), width=int(width * SS))
        else:
            self.d.arc(box, start, start + sweep, fill=color, width=int(width * SS))
        hw = width / 2
        for angle, f in ((start, 0.0), (start + sweep, 1.0)):
            rad = math.radians(angle)
            self.dot(cx + (r - hw) * math.cos(rad), cy + (r - hw) * math.sin(rad), hw, color_at(f))

    def gradient_bar(self, box, radius, color_at):
        x0, y0, x1, y1 = [int(v * SS) for v in box]
        w, h = x1 - x0, y1 - y0
        if w < 1 or h < 1:
            return
        strip = Image.new('RGB', (w, 1))
        strip.putdata([color_at(i / max(w - 1, 1)) for i in range(w)])
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(radius * SS), fill=255)
        self.img.paste(strip.resize((w, h)), (x0, y0), mask)

    def vgradient(self, box, top, bottom):
        x0, y0, x1, y1 = [int(v * SS) for v in box]
        mask = Image.linear_gradient('L').resize((x1 - x0, y1 - y0))
        self.img.paste(Image.composite(Image.new('RGB', mask.size, bottom), Image.new('RGB', mask.size, top), mask), (x0, y0))

    def overlay(self, box, radius, color, alpha, outline_alpha=0.0):
        mask = Image.new('L', self.img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([v * SS for v in box], radius=radius * SS, fill=int(255 * alpha))
        if outline_alpha:
            draw.rounded_rectangle([v * SS for v in box], radius=radius * SS, outline=int(255 * outline_alpha), width=SS)
        self.img.paste(Image.new('RGB', self.img.size, color), (0, 0), mask)


    def chart_points(self, box, values, vmin, vmax):
        x0, y0, x1, y1 = box
        span = max(vmax - vmin, 1e-6)
        n = max(len(values) - 1, 1)
        return [(x0 + (x1 - x0) * i / n, y1 - (y1 - y0) * clamp01((v - vmin) / span)) for i, v in enumerate(values)]

    def area_chart(self, box, values, vmin, vmax, color, fill_strength, line_strength=1.0):
        if len(values) < 2:
            return
        x0, y0, x1, y1 = box
        pts = [(x * SS, y * SS) for x, y in self.chart_points(box, values, vmin, vmax)]
        shape = Image.new('L', self.img.size, 0)
        ImageDraw.Draw(shape).polygon(pts + [(x1 * SS, y1 * SS), (x0 * SS, y1 * SS)], fill=255)
        fade = Image.new('L', self.img.size, 0)
        grad = Image.linear_gradient('L').resize((int((x1 - x0) * SS), int((y1 - y0) * SS)))
        fade.paste(grad.point(lambda v: int((255 - v) * fill_strength)), (int(x0 * SS), int(y0 * SS)))
        self.img.paste(Image.new('RGB', self.img.size, color), (0, 0), ImageChops.multiply(shape, fade))
        self.d.line(pts, fill=mix(color, self.pal.bg, line_strength), width=int(1.6 * SS), joint='curve')

    def glow(self, paint, radius=6, strength=1.0):
        base = self.img
        self.img = Image.new('RGB', base.size, (0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        paint()
        # blurring at 1x is much faster
        halo = self.img.resize((WIDTH, HEIGHT), Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(radius))
        halo = halo.resize(base.size, Image.Resampling.BICUBIC)
        if strength != 1.0:
            halo = halo.point(lambda v: min(255, int(v * strength)))
        self.img = ImageChops.add(base, halo)
        self.d = ImageDraw.Draw(self.img)
        paint()

    def finish(self, scale=1):
        return self.img.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.LANCZOS)
