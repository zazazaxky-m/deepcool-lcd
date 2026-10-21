import datetime
import math

from PIL import Image, ImageDraw, ImageFilter

from .config import THEMES
from .device import HEIGHT, WIDTH
from .render import (ICON_CPU, ICON_GPU, ICON_RAM, RAM_COLOR, RENDER_LOCK, SS, Canvas, Palette, clamp01,
                     fmt_clock, fmt_date, fmt_temp, fmt_uptime, mix, temp_color)


def device_names(config, names):
    return (config['cpu_label'] or names.cpu_name, config['gpu_label'] or names.gpu_name)


def theme_gauge(c, info, history, config, names, now):
    pal = c.pal
    for cx, name, icon, accent, temp, load, clock in (
            (82, 'CPU', ICON_CPU, pal.cpu, info['cpu_temp'], info['cpu_percent'], info['cpu_freq']),
            (238, 'GPU', ICON_GPU, pal.gpu, info['gpu_temp'], info['gpu_util'], info['gpu_clock'])):
        cy, r, start, total = 100, 70, 135, 270
        c.arc(cx, cy, r, 11, start, total, pal.track)
        c.arc(cx, cy, r, 11, start, total * clamp01(temp / 100), lambda f, t=temp: temp_color(20 + (t - 20) * f))
        c.arc(cx, cy, r - 18, 4, start, total, pal.border)
        c.arc(cx, cy, r - 18, 4, start, total * clamp01(max(load, 1) / 100), accent)
        temp_text = fmt_temp(temp, config)
        size = c.fit_size(temp_text, 'Bold', 44, 80)
        c.text((cx + 5, cy + 4), temp_text, 'Bold', size, temp_color(temp), anchor='ms')
        c.labeled((cx, cy + 24), icon, name, 'SemiBold', 13, accent, accent, anchor='ms')
        c.text((cx, cy + 62), f"{load:.0f}%", 'SemiBold', 17, pal.text, anchor='ms')
        c.text((cx, cy + 80), f"{clock:.2f} GHz", 'Regular', 13, pal.muted, anchor='ms')
    c.rect([12, 200, 308, 230], 9, fill=pal.card)
    c.labeled((22, 220), ICON_RAM, f"{info['ram_used']:.1f}/{info['ram_total']:.0f} GB", 'Medium', 13, pal.text, pal.muted)
    c.bar(140, 211, 100, 8, info['ram_percent'] / 100, RAM_COLOR)
    c.text((298, 221), fmt_clock(now, config), 'SemiBold', 16, pal.text, anchor='rs')


def theme_hero(c, info, history, config, names, now):
    pal = c.pal
    cpu_name, gpu_name = device_names(config, names)
    if config['hero_focus'] == 'gpu':
        name, icon, accent, temp, temps = gpu_name, ICON_GPU, pal.gpu, info['gpu_temp'], history['gpu_temp']
        chips = [('GPU', f"{info['gpu_util']:.0f}%", '', accent, info['gpu_util'] / 100),
                 ('CLOCK', f"{info['gpu_clock']:.2f}", 'GHz', accent, info['gpu_clock'] / (info['gpu_clock_max'] or 3)),
                 ('CPU', fmt_temp(info['cpu_temp'], config), '', temp_color(info['cpu_temp']), info['cpu_temp'] / 100)]
    else:
        name, icon, accent, temp, temps = cpu_name, ICON_CPU, pal.cpu, info['cpu_temp'], history['cpu_temp']
        chips = [('CPU', f"{info['cpu_percent']:.0f}%", '', accent, info['cpu_percent'] / 100),
                 ('CLOCK', f"{info['cpu_freq']:.2f}", 'GHz', accent, info['cpu_freq'] / (info['cpu_freq_max'] or 5)),
                 ('GPU', fmt_temp(info['gpu_temp'], config), '', temp_color(info['gpu_temp']), info['gpu_temp'] / 100)]
    color = temp_color(temp)
    if len(temps) >= 2:
        lo = min(temps) - 4
        c.area_chart((0, 70, WIDTH, 156), temps, lo, lo + max(max(temps) - lo, 10), color, 0.28, 0.5)
    c.labeled((16, 26), icon, name.upper(), 'SemiBold', 13, pal.muted, accent)
    c.text((304, 26), fmt_clock(now, config), 'SemiBold', 16, pal.text, anchor='rs')
    value = fmt_temp(temp, config).rstrip('°')
    size = c.fit_size(value, 'Bold', 100, 200)
    c.text((150, 132), value, 'Bold', size, color, anchor='ms')
    unit = '°F' if config['temp_unit'] == 'F' else '°C'
    c.text((150 + c.text_width(value, 'Bold', size) / 2 + 4, 132 - size * 0.62), unit, 'Medium', 24, pal.muted, anchor='ls')
    x, w, gap = 12, 92, 8
    for label, value, unit, chip_color, frac in chips:
        c.rect([x, 164, x + w, 228], 10, fill=pal.card)
        c.text((x + 10, 182), label, 'SemiBold', 10, pal.muted, anchor='ls')
        c.text((x + 10, 208), value, 'Bold', 22, pal.text, anchor='ls')
        if unit:
            c.text((x + 13 + c.text_width(value, 'Bold', 22), 208), unit, 'Medium', 11, pal.muted, anchor='ls')
        c.bar(x + 10, 215, w - 20, 5, frac, chip_color)
        x += w + gap


def theme_dashboard(c, info, history, config, names, now):
    pal = c.pal
    cpu_name, gpu_name = device_names(config, names)
    cpu_stats = [(f"{info['cpu_percent']:.0f}%", 'load'), (f"{info['cpu_freq']:.2f}", 'GHz'),
                 (f"{info['cpu_power']:.0f}", 'W') if info.get('cpu_power') else None,
                 (f"{info['ram_used']:.1f}", 'GB RAM')]
    gpu_stats = [(f"{info['gpu_util']:.0f}%", 'load'), (f"{info['gpu_clock']:.2f}", 'GHz'),
                 (f"{info['gpu_power']:.0f}", 'W') if info['gpu_power'] > 0 else None,
                 (f"{info['vram_used']:.1f}", 'GB VRAM') if info['vram_total'] > 0 else None]
    columns = [i for i in range(4) if cpu_stats[i] or gpu_stats[i]]
    size, unit_size, gap = 16, 11, 16

    def stat_width(stat, size, unit_size):
        return c.text_width(stat[0], 'Bold', size) + 3 + c.text_width(stat[1], 'Regular', unit_size) if stat else 0

    while True:
        widths = [max(stat_width(cpu_stats[i], size, unit_size), stat_width(gpu_stats[i], size, unit_size)) for i in columns]
        if sum(widths) + gap * (len(widths) - 1) <= 280 or size <= 11:
            break
        size, unit_size, gap = size - 1, max(unit_size - 1, 9), max(gap - 2, 8)
    column_x = [20 + sum(widths[:n]) + gap * n for n in range(len(columns))]
    rows = [
        (8, ICON_CPU, cpu_name, pal.cpu, info['cpu_temp'], history['cpu_percent'], cpu_stats),
        (124, ICON_GPU, gpu_name, pal.gpu, info['gpu_temp'], history['gpu_util'], gpu_stats),
    ]
    for y, icon, name, accent, temp, loads, stats in rows:
        c.rect([8, y, 312, y + 108], 12, fill=pal.card)
        c.labeled((20, y + 23), icon, name, 'SemiBold', 14, pal.text, accent)
        temp_text = fmt_temp(temp, config)
        c.text((300, y + 44), temp_text, 'Bold', c.fit_size(temp_text, 'Bold', 40, 96), temp_color(temp), anchor='rs')
        c.text((300, y + 62), 'temp', 'Regular', 11, pal.muted, anchor='rs')
        c.area_chart((20, y + 34, 196, y + 72), loads, 0, 100, accent, 0.30)
        c.d.line([(20 * SS, (y + 72) * SS), (196 * SS, (y + 72) * SS)], fill=pal.border, width=SS)
        for x, i in zip(column_x, columns):
            if stats[i]:
                value, unit = stats[i]
                c.text((x, y + 96), value, 'Bold', size, pal.text, anchor='ls')
                c.text((x + c.text_width(value, 'Bold', size) + 3, y + 96), unit, 'Regular', unit_size, pal.muted, anchor='ls')


def focused(info, config, pal):
    cpu = {'name': 'CPU', 'icon': ICON_CPU, 'accent': pal.cpu, 'temp': info['cpu_temp'],
           'load': info['cpu_percent'], 'clock': info['cpu_freq']}
    gpu = {'name': 'GPU', 'icon': ICON_GPU, 'accent': pal.gpu, 'temp': info['gpu_temp'],
           'load': info['gpu_util'], 'clock': info['gpu_clock']}
    return (gpu, cpu) if config['hero_focus'] == 'gpu' else (cpu, gpu)


def both(info, pal):
    return (('CPU', ICON_CPU, pal.cpu, info['cpu_temp'], info['cpu_percent'], info['cpu_freq']),
            ('GPU', ICON_GPU, pal.gpu, info['gpu_temp'], info['gpu_util'], info['gpu_clock']))


def theme_minimal(c, info, history, config, names, now):
    pal = c.pal
    c.text((160, 34), fmt_clock(now, config), 'Medium', 13, pal.muted, anchor='ms')
    c.line([(160, 72), (160, 196)], pal.border)
    for cx, (name, _icon, accent, temp, load, clock) in zip((80, 240), both(info, pal)):
        label_w = c.text_width(name, 'SemiBold', 11)
        c.dot(cx - label_w / 2 - 2, 81, 3, accent)
        c.text((cx + 5, 85), name, 'SemiBold', 11, pal.muted, anchor='ms')
        value = fmt_temp(temp, config).rstrip('°')
        size = c.fit_size(value, 'Light', 72, 112)
        deg_size = size // 2
        value_w, deg_w = c.text_width(value, 'Light', size), c.text_width('°', 'Regular', deg_size)
        x = cx - (value_w + deg_w) / 2
        c.text((x, 152), value, 'Light', size, pal.text, anchor='ls')
        c.text((x + value_w + 1, 152 - size * 0.35), '°', 'Regular', deg_size, accent, anchor='ls')
        c.bar(cx - 34, 168, 68, 3, load / 100, accent)
        c.text((cx, 192), f"{load:.0f}%  ·  {clock:.2f} GHz", 'Regular', 11, pal.muted, anchor='ms')


def theme_rings(c, info, history, config, names, now):
    pal = c.pal
    cx, cy = 106, 120
    rings = [('CPU', pal.cpu, info['cpu_percent'], f"{fmt_temp(info['cpu_temp'], config)}  ·  {info['cpu_freq']:.2f} GHz"),
             ('GPU', pal.gpu, info['gpu_util'], f"{fmt_temp(info['gpu_temp'], config)}  ·  {info['gpu_clock']:.2f} GHz"),
             ('RAM', RAM_COLOR, info['ram_percent'], f"{info['ram_used']:.1f} / {info['ram_total']:.0f} GB")]
    for i, (name, color, load, sub) in enumerate(rings):
        r = 98 - i * 21
        c.arc(cx, cy, r, 15, -90, 360, mix(color, pal.bg, 0.2))
        c.arc(cx, cy, r, 15, -90, 360 * clamp01(max(load, 1.5) / 100), color)
        y = 52 + i * 66
        c.dot(220, y - 4, 3.5, color)
        c.text((229, y), name, 'SemiBold', 10, pal.muted, anchor='ls')
        c.text((215, y + 28), f"{load:.0f}%", 'Bold', 26, pal.text, anchor='ls')
        c.text((216, y + 44), sub, 'Regular', 10, pal.muted, anchor='ls')
    c.text((cx, cy + 7), fmt_clock(now, config), 'SemiBold', 18, pal.text, anchor='ms')


def theme_speedo(c, info, history, config, names, now):
    pal = c.pal
    main, other = focused(info, config, pal)
    cx, cy, r, start, sweep = 160, 128, 106, 150, 240
    temp = main['temp']
    frac = clamp01(temp / 100)
    c.arc(cx, cy, r, 7, start, sweep, lambda f: mix(temp_color(f * 100), pal.bg, 0.2))
    c.arc(cx, cy, r, 7, start, sweep * frac, lambda f: temp_color(f * temp))
    for v in range(0, 101, 5):
        a = math.radians(start + sweep * v / 100)
        major = v % 20 == 0
        r0, r1 = r - 13, r - (25 if major else 19)
        lit = v <= temp
        color = (pal.text if lit else pal.muted) if major else mix(pal.text if lit else pal.muted, pal.bg, 0.55)
        c.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
               color, 1.8 if major else 1.1)
        if major:
            label = f"{v * 9 / 5 + 32:.0f}" if config['temp_unit'] == 'F' else str(v)
            c.text((cx + (r - 37) * math.cos(a), cy + (r - 37) * math.sin(a)), label, 'Medium', 10, pal.muted, anchor='mm')
    # needle
    a = math.radians(start + sweep * frac)
    ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    tip = (cx + (r - 17) * ux, cy + (r - 17) * uy)
    tail = [(cx - 12 * ux + 4.5 * nx, cy - 12 * uy + 4.5 * ny), (cx - 12 * ux - 4.5 * nx, cy - 12 * uy - 4.5 * ny)]
    c.d.polygon([(x * SS, y * SS) for x, y in [tip] + tail], fill=main['accent'])
    c.dot(cx, cy, 9, main['accent'])
    c.dot(cx, cy, 4, pal.bg)
    c.text((160, 206), fmt_temp(temp, config), 'Bold', 40, temp_color(temp), anchor='ms')
    c.text((160, 224), main['name'], 'SemiBold', 11, pal.muted, anchor='ms')
    c.text((16, 24), f"{main['clock']:.2f} GHz", 'Medium', 12, pal.muted, anchor='ls')
    c.text((304, 24), fmt_clock(now, config), 'Medium', 12, pal.muted, anchor='rs')
    c.text((16, 210), 'LOAD', 'SemiBold', 9, pal.muted, anchor='ls')
    c.text((16, 230), f"{main['load']:.0f}%", 'Bold', 17, pal.text, anchor='ls')
    c.text((304, 210), other['name'], 'SemiBold', 9, pal.muted, anchor='rs')
    c.text((304, 230), fmt_temp(other['temp'], config), 'Bold', 17, temp_color(other['temp']), anchor='rs')


def theme_tiles(c, info, history, config, names, now):
    pal = c.pal
    if info['gpu_power'] > 0:
        gpu_last = ('POWER', f"{info['gpu_power']:.0f}", 'W', pal.text,
                    ('bar', info['gpu_power'] / (info['gpu_power_limit'] or 300), pal.gpu))
    else:
        gpu_last = ('VRAM', f"{info['vram_used']:.1f}", 'GB', pal.text,
                    ('bar', info['vram_used'] / (info['vram_total'] or 1), pal.gpu))
    tiles = [
        (ICON_CPU, pal.cpu, 'TEMP', fmt_temp(info['cpu_temp'], config), '', temp_color(info['cpu_temp']),
         ('bar', info['cpu_temp'] / 100, temp_color(info['cpu_temp']))),
        (ICON_CPU, pal.cpu, 'LOAD', f"{info['cpu_percent']:.0f}", '%', pal.text, ('spark', history['cpu_percent'], pal.cpu)),
        (ICON_CPU, pal.cpu, 'CLOCK', f"{info['cpu_freq']:.2f}", 'GHz', pal.text,
         ('bar', info['cpu_freq'] / (info['cpu_freq_max'] or 5), pal.cpu)),
        (ICON_GPU, pal.gpu, 'TEMP', fmt_temp(info['gpu_temp'], config), '', temp_color(info['gpu_temp']),
         ('bar', info['gpu_temp'] / 100, temp_color(info['gpu_temp']))),
        (ICON_GPU, pal.gpu, 'LOAD', f"{info['gpu_util']:.0f}", '%', pal.text, ('spark', history['gpu_util'], pal.gpu)),
        (ICON_GPU, pal.gpu) + gpu_last,
    ]
    w, h = 96, 108
    for i, (icon, accent, label, value, unit, value_color, extra) in enumerate(tiles):
        x, y = 8 + (i % 3) * 104, 8 + (i // 3) * 116
        c.rect([x, y, x + w, y + h], 12, fill=pal.card)
        c.labeled((x + 10, y + 21), icon, label, 'SemiBold', 10, pal.muted, accent)
        unit_w = c.text_width(unit, 'Medium', 11) + 3 if unit else 0
        size = c.fit_size(value, 'Bold', 30, w - 20 - unit_w)
        c.text((x + 10, y + 64), value, 'Bold', size, value_color, anchor='ls')
        if unit:
            c.text((x + 13 + c.text_width(value, 'Bold', size), y + 64), unit, 'Medium', 11, pal.muted, anchor='ls')
        kind, data, color = extra
        if kind == 'bar':
            c.bar(x + 10, y + 86, w - 20, 5, data, color)
        elif len(data) >= 2:
            c.area_chart((x + 10, y + 74, x + w - 10, y + 96), data, 0, max(25, max(data) * 1.2), color, 0.32)


def theme_cores(c, info, history, config, names, now):
    pal = c.pal
    cpu_name, _ = device_names(config, names)
    c.labeled((14, 27), ICON_CPU, cpu_name, 'SemiBold', 13, pal.text, pal.cpu)
    c.text((306, 31), fmt_temp(info['cpu_temp'], config), 'Bold', 26, temp_color(info['cpu_temp']), anchor='rs')
    cores = list(info['cpu_cores']) or [info['cpu_percent']]
    while len(cores) > 32:
        cores = [(a + b) / 2 for a, b in zip(cores[::2], cores[1::2])]
    x0, x1, top, bottom = 14, 306, 48, 166
    gap = 4 if len(cores) <= 16 else 2
    w = (x1 - x0 - gap * (len(cores) - 1)) / len(cores)
    radius = min(w / 2, 4)
    for i, load in enumerate(cores):
        x = x0 + i * (w + gap)
        c.rect([x, top, x + w, bottom], radius, fill=pal.card)
        h = max((bottom - top) * clamp01(load / 100), radius * 2)
        color = mix((255, 128, 64), pal.cpu, clamp01((load - 60) / 40))
        c.rect([x, bottom - h, x + w, bottom], radius, fill=color)
    c.rect([14, 180, 306, 228], 11, fill=pal.card)
    stats = [('LOAD', f"{info['cpu_percent']:.0f}%", '', pal.text),
             ('CLOCK', f"{info['cpu_freq']:.2f}", 'GHz', pal.text),
             ('GPU', fmt_temp(info['gpu_temp'], config), '', temp_color(info['gpu_temp']))]
    for i, (label, value, unit, color) in enumerate(stats):
        x = 28 + i * 98
        c.text((x, 197), label, 'SemiBold', 9, pal.muted, anchor='ls')
        c.text((x, 219), value, 'Bold', 17, color, anchor='ls')
        if unit:
            c.text((x + c.text_width(value, 'Bold', 17) + 3, 219), unit, 'Medium', 10, pal.muted, anchor='ls')


def theme_timeline(c, info, history, config, names, now):
    pal = c.pal
    for x, (name, _icon, color, temp, _load, _clock) in zip((16, 104), both(info, pal)):
        c.dot(x + 3, 21, 3, color)
        c.text((x + 11, 25), name, 'SemiBold', 10, pal.muted, anchor='ls')
        c.text((x, 53), fmt_temp(temp, config), 'Bold', 26, pal.text, anchor='ls')
    c.text((304, 25), fmt_clock(now, config), 'Medium', 13, pal.muted, anchor='rs')
    cpu, gpu = history['cpu_temp'], history['gpu_temp']
    values = cpu + gpu
    if not values:
        return
    lo = math.floor((min(values) - 3) / 5) * 5
    hi = max(math.ceil((max(values) + 3) / 5) * 5, lo + 15)
    box = (16, 72, 280, 204)
    for v in (lo, (lo + hi) / 2, hi):
        y = box[3] - (box[3] - box[1]) * (v - lo) / (hi - lo)
        c.line([(box[0], y), (box[2], y)], pal.border)
        c.text((304, y + 4), fmt_temp(v, config), 'Regular', 9, pal.muted, anchor='rs')
    for series, color, fill in ((gpu, pal.gpu, 0.14), (cpu, pal.cpu, 0.22)):
        if len(series) >= 2:
            c.area_chart(box, series, lo, hi, color, fill)
            x, y = c.chart_points(box, series, lo, hi)[-1]
            c.dot(x, y, 4.5, pal.bg)
            c.dot(x, y, 3, color)
    times = history['time']
    span = times[-1] - times[0] if len(times) > 1 else 0
    c.text((16, 224), f"−{span / 60:.0f} min" if span >= 90 else f"−{span:.0f} s", 'Regular', 9, pal.muted, anchor='ls')
    c.text((280, 224), 'now', 'Regular', 9, pal.muted, anchor='rs')


def theme_split(c, info, history, config, names, now):
    pal = c.pal
    for x0, (name, icon, accent, temp, load, clock) in zip((0, 160), both(info, pal)):
        c.vgradient([x0, 0, x0 + 160, HEIGHT], mix(accent, pal.bg, 0.34), mix(accent, pal.bg, 0.05))
        cx = x0 + 80
        c.labeled((cx, 38), icon, name, 'SemiBold', 13, pal.text, accent, anchor='ms')
        value = fmt_temp(temp, config)
        c.text((cx + 4, 120), value, 'Bold', c.fit_size(value, 'Bold', 60, 136), pal.text, anchor='ms')
        c.text((cx, 150), f"{load:.0f}% load", 'Medium', 13, pal.text, anchor='ms')
        c.text((cx, 170), f"{clock:.2f} GHz", 'Regular', 12, pal.muted, anchor='ms')
        c.rect([x0 + 20, 200, x0 + 140, 206], 3, fill=mix(pal.text, mix(accent, pal.bg, 0.1), 0.12))
        if load > 0.5:
            c.rect([x0 + 20, 200, x0 + 20 + max(6, 120 * clamp01(load / 100)), 206], 3, fill=accent)
    c.line([(160, 0), (160, HEIGHT)], pal.bg, 1.5)


def theme_aurora(c, info, history, config, names, now):
    pal = c.pal
    small = Image.new('RGB', (80, 60), pal.bg)
    blobs = ImageDraw.Draw(small)
    blobs.ellipse([-26, -30, 42, 34], fill=pal.cpu)
    blobs.ellipse([42, 24, 112, 88], fill=pal.gpu)
    blobs.ellipse([48, -24, 88, 12], fill=mix(RAM_COLOR, pal.bg, 0.8))
    small = Image.blend(Image.new('RGB', small.size, pal.bg), small.filter(ImageFilter.GaussianBlur(13)),
                        0.8 if pal.dark else 0.55)
    c.img.paste(small.resize(c.img.size, Image.Resampling.BICUBIC))
    soft = mix(pal.text, pal.bg, 0.72)
    c.text((20, 37), fmt_clock(now, config), 'SemiBold', 22, pal.text, anchor='ls')
    c.text((300, 35), fmt_date(now, short=True), 'Medium', 12, soft, anchor='rs')
    glass = (255, 255, 255)
    c.overlay([16, 52, 304, 224], 18, glass, 0.08 if pal.dark else 0.45, 0.16 if pal.dark else 0.6)
    c.overlay([159.5, 80, 160.5, 196], 0, glass, 0.14 if pal.dark else 0.5)
    for cx, (name, icon, accent, temp, load, clock) in zip((88, 232), both(info, pal)):
        c.labeled((cx, 86), icon, name, 'SemiBold', 12, pal.text, accent, anchor='ms')
        value = fmt_temp(temp, config)
        c.text((cx + 3, 142), value, 'Bold', c.fit_size(value, 'Bold', 50, 120), pal.text, anchor='ms')
        c.text((cx, 166), f"{load:.0f}%  ·  {clock:.2f} GHz", 'Regular', 11, soft, anchor='ms')
        c.overlay([cx - 50, 186, cx + 50, 191], 2.5, glass, 0.16 if pal.dark else 0.6)
        if load > 0.5:
            c.rect([cx - 50, 186, cx - 50 + max(5, 100 * clamp01(load / 100)), 191], 2.5, fill=accent)


def theme_neon(c, info, history, config, names, now):
    pal = c.pal
    chart = (16, 140, 304, 206)
    loads = history['cpu_percent'] + history['gpu_util']
    top = max(25, max(loads) * 1.15) if loads else 100

    def paint():
        c.text((18, 32), 'CPU', 'SemiBold', 12, pal.cpu, anchor='ls')
        c.text((302, 32), 'GPU', 'SemiBold', 12, pal.gpu, anchor='rs')
        c.text((15, 94), fmt_temp(info['cpu_temp'], config), 'Bold', 56, pal.cpu, anchor='ls')
        c.text((305, 94), fmt_temp(info['gpu_temp'], config), 'Bold', 56, pal.gpu, anchor='rs')
        for values, color in ((history['gpu_util'], pal.gpu), (history['cpu_percent'], pal.cpu)):
            if len(values) >= 2:
                c.line(c.chart_points(chart, values, 0, top), color, 2)

    c.line([(chart[0], chart[3] + 1), (chart[2], chart[3] + 1)], pal.border)
    if pal.dark:
        c.glow(paint, radius=6, strength=1.15)
    else:
        paint()
    c.text((18, 117), f"{info['cpu_percent']:.0f}%  ·  {info['cpu_freq']:.2f} GHz", 'Regular', 11, pal.muted, anchor='ls')
    c.text((302, 117), f"{info['gpu_util']:.0f}%  ·  {info['gpu_clock']:.2f} GHz", 'Regular', 11, pal.muted, anchor='rs')
    c.text((160, 229), fmt_clock(now, config), 'Medium', 12, pal.muted, anchor='ms')


def theme_thermo(c, info, history, config, names, now):
    pal = c.pal
    cpu_name, gpu_name = device_names(config, names)
    c.text((20, 22), 'TEMPERATURE', 'SemiBold', 9, pal.muted, anchor='ls')
    c.text((304, 22), fmt_clock(now, config), 'Medium', 12, pal.muted, anchor='rs')
    x0, x1 = 36, 300
    for yc, label, (_name, icon, accent, temp, load, clock) in zip((84, 182), (cpu_name, gpu_name), both(info, pal)):
        c.labeled((20, yc - 28), icon, label, 'SemiBold', 13, pal.text, accent)
        c.text((20, yc - 11), f"{load:.0f}% load  ·  {clock:.2f} GHz", 'Regular', 10, pal.muted, anchor='ls')
        c.text((304, yc - 9), fmt_temp(temp, config), 'Bold', 30, temp_color(temp), anchor='rs')
        t0, t1 = yc + 3, yc + 15
        c.rect([x0, t0, x1, t1], 6, fill=pal.track)
        fill_x = max(x0 + 12, x0 + (x1 - x0) * clamp01(temp / 100))
        c.gradient_bar([x0, t0, fill_x, t1], 6, lambda f, t=temp: temp_color(25 + (t - 25) * f))
        c.dot(x0 - 1, yc + 9, 11, temp_color(25))
        for v in range(10, 101, 10):
            x = x0 + (x1 - x0) * v / 100
            c.line([(x, t1 + 5), (x, t1 + (10 if v % 50 == 0 else 8))], pal.muted if v % 50 == 0 else pal.border, 1.2)
            if v % 20 == 0:
                c.text((x, t1 + 21), fmt_temp(v, config), 'Regular', 8, pal.muted, anchor='ms')


def theme_clock(c, info, history, config, names, now):
    pal = c.pal
    text = fmt_clock(now, config)
    size = c.fit_size(text, 'Light', 92, 270)
    if config['clock_24h']:
        c.text((160, 124), text, 'Light', size, pal.text, anchor='ms')
    else:
        ampm = now.strftime('%p')
        text_w, ampm_w = c.text_width(text, 'Light', size), c.text_width(ampm, 'Medium', 16)
        x = 160 - (text_w + ampm_w + 6) / 2
        c.text((x, 124), text, 'Light', size, pal.text, anchor='ls')
        c.text((x + text_w + 6, 124), ampm, 'Medium', 16, pal.muted, anchor='ls')
    c.text((160, 156), fmt_date(now), 'Medium', 14, pal.muted, anchor='ms')
    pills = [('CPU', pal.cpu, info['cpu_temp']), ('GPU', pal.gpu, info['gpu_temp'])]
    widths = [c.text_width(f"{name}  {fmt_temp(temp, config)}", 'SemiBold', 14) + 36 for name, _, temp in pills]
    x = 160 - (sum(widths) + 10) / 2
    for (name, color, temp), w in zip(pills, widths):
        c.rect([x, 182, x + w, 214], 16, fill=pal.card)
        c.dot(x + 15, 198, 4, color)
        c.text((x + 25, 203), name, 'SemiBold', 14, pal.muted, anchor='ls')
        c.text((x + w - 13, 203), fmt_temp(temp, config), 'SemiBold', 14, pal.text, anchor='rs')
        x += w + 10


TERMINAL_GREEN = (90, 250, 150)


def theme_terminal(c, info, history, config, names, now):
    pal = c.pal
    green = TERMINAL_GREEN if pal.dark else (20, 130, 60)
    dim = mix(green, pal.bg, 0.5)
    hot = (255, 90, 80)
    cpu_name, gpu_name = device_names(config, names)

    def meter(frac, n=12):
        filled = round(clamp01(frac) * n)
        return '[' + '|' * filled + '.' * (n - filled) + ']'

    def temp_part(temp):
        return (fmt_temp(temp, config), hot if temp >= 80 else green)

    gpu_extra = f"{info['gpu_power']:.0f} W  " if info['gpu_power'] > 0 else ''
    cpu_extra = f"{info['cpu_power']:.0f} W  " if info.get('cpu_power') else ''
    lines = [
        [('$ ', dim), ('deepcool-lcd status', green)],
        [('CPU ', green), (meter(info['cpu_percent'] / 100), green), (f" {info['cpu_percent']:3.0f}%  ", green), temp_part(info['cpu_temp'])],
        [(f"    {info['cpu_freq']:.2f} GHz  {cpu_extra}{cpu_name}", dim)],
        [('GPU ', green), (meter(info['gpu_util'] / 100), green), (f" {info['gpu_util']:3.0f}%  ", green), temp_part(info['gpu_temp'])],
        [(f"    {info['gpu_clock']:.2f} GHz  {gpu_extra}{gpu_name}", dim)],
        [('MEM ', green), (meter(info['ram_percent'] / 100), green), (f" {info['ram_percent']:3.0f}%  ", green), (f"{info['ram_used']:.1f}G", green)],
        [],
        [(f"{fmt_clock(now, config)}  up {fmt_uptime(info['uptime'])}", dim)],
        [('$ ', dim)],
    ]
    size, y, step = 13, 26, 22
    x = 14
    for row in lines:
        x = 14
        for text, color in row:
            c.text((x, y), text, 'Mono', size, color, anchor='ls')
            x += c.text_width(text, 'Mono', size)
        y += step
    if now.second % 4 < 2:  # blinking cursor
        c.rect([x + 1, y - step - 11, x + 9, y - step + 3], 0, fill=green)
    if pal.dark:  # scanlines
        for sy in range(0, HEIGHT * SS, 3 * SS):
            c.d.line([(0, sy), (WIDTH * SS, sy)], fill=(0, 0, 0), width=1)


THEME_RENDERERS = {
    'gauge': theme_gauge, 'hero': theme_hero, 'dashboard': theme_dashboard, 'minimal': theme_minimal,
    'rings': theme_rings, 'speedo': theme_speedo, 'tiles': theme_tiles, 'cores': theme_cores,
    'timeline': theme_timeline, 'split': theme_split, 'aurora': theme_aurora, 'neon': theme_neon,
    'thermo': theme_thermo, 'clock': theme_clock, 'terminal': theme_terminal,
}
assert set(THEME_RENDERERS) == set(THEMES)


def render_frame(info, history, config, names, now=None, scale=1):
    with RENDER_LOCK:
        canvas = Canvas(Palette(config))
        THEME_RENDERERS[config['theme']](canvas, info, history, config, names, now or datetime.datetime.now())
        return canvas.finish(scale)
