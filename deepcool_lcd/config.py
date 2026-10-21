import json
import os
import re
import sys

from . import paths

THEME_NAMES = {
    'gauge': 'Gauge',
    'hero': 'Big Number',
    'dashboard': 'Dashboard',
    'minimal': 'Minimal',
    'rings': 'Rings',
    'speedo': 'Speedometer',
    'tiles': 'Tiles',
    'cores': 'Cores',
    'timeline': 'Timeline',
    'split': 'Split',
    'aurora': 'Aurora',
    'neon': 'Neon',
    'thermo': 'Thermometer',
    'clock': 'Clock',
    'terminal': 'Terminal',
}
THEMES = tuple(THEME_NAMES)
FOCUS_THEMES = ('hero', 'speedo')  # themes that use hero_focus

BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_STEP = 10, 100, 10
INTERVALS = (0.5, 1, 2, 3, 4, 5)  # seconds
# don't change what's drawn
DEVICE_SETTINGS = ('brightness', 'interval')

DEFAULT_CONFIG = {
    'theme': 'gauge',
    'cpu_color': '#40c4ff',
    'gpu_color': '#76e06f',
    'background': '#090b10',
    'temp_unit': 'C',
    'clock_24h': True,
    'cpu_label': '',  # empty = detected model name
    'gpu_label': '',
    'hero_focus': 'cpu',
    'brightness': 100,
    'interval': 2,
}

HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def validate_value(key, value):
    if key == 'theme':
        if value not in THEMES:
            raise ValueError(f"theme must be one of {', '.join(THEMES)}")
    elif key in ('cpu_color', 'gpu_color', 'background'):
        if not isinstance(value, str) or not HEX_COLOR.match(value):
            raise ValueError(f"{key} must be a color like #40c4ff")
        value = value.lower()
    elif key == 'temp_unit':
        if value not in ('C', 'F'):
            raise ValueError("temp_unit must be C or F")
    elif key == 'clock_24h':
        if not isinstance(value, bool):
            raise ValueError("clock_24h must be true or false")
    elif key in ('cpu_label', 'gpu_label'):
        if not isinstance(value, str) or len(value) > 24 or not value.isprintable():
            raise ValueError(f"{key} must be text of at most 24 characters")
        value = value.strip()
    elif key == 'hero_focus':
        if value not in ('cpu', 'gpu'):
            raise ValueError("hero_focus must be cpu or gpu")
    elif key == 'brightness':
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int) or not BRIGHTNESS_MIN <= value <= BRIGHTNESS_MAX:
            raise ValueError(f"brightness must be a whole number from {BRIGHTNESS_MIN} to {BRIGHTNESS_MAX}")
    elif key == 'interval':
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in INTERVALS:
            raise ValueError(f"interval must be one of {', '.join(str(v) for v in INTERVALS)} seconds")
        value = int(value) if float(value).is_integer() else float(value)
    return value


def merge_config(base, changes, strict=True):
    config = dict(base)
    for key, value in changes.items():
        try:
            if key not in DEFAULT_CONFIG:
                raise ValueError(f"unknown setting: {key}")
            config[key] = validate_value(key, value)
        except ValueError as e:
            if strict:
                raise
            print(f"Ignoring setting {key!r}: {e}", file=sys.stderr)
    return config


def _read(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('not a JSON object')
    return merge_config(DEFAULT_CONFIG, data, strict=False)


def load_config():
    for path in (paths.CONFIG_PATH, paths.LEGACY_CONFIG_PATH):
        try:
            return _read(path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as e:
            print(f"Could not read {path}: {e}", file=sys.stderr)
            break
    return dict(DEFAULT_CONFIG)


def save_config(config):
    os.makedirs(os.path.dirname(paths.CONFIG_PATH), exist_ok=True)
    tmp = paths.CONFIG_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
    os.chmod(tmp, 0o644)
    os.replace(tmp, paths.CONFIG_PATH)
