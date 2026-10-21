import os
from pathlib import Path

try:
    from ._build_paths import DATA_DIR  # written by `make install`
except ImportError:
    DATA_DIR = str(Path(__file__).resolve().parent.parent / 'data')  # running from a source checkout

DATA_DIR = os.environ.get('DEEPCOOL_LCD_DATA_DIR', DATA_DIR)
FONT_DIR = os.path.join(DATA_DIR, 'fonts')

CONFIG_PATH = os.environ.get('DEEPCOOL_LCD_CONFIG', '/etc/deepcool-lcd/config.json')
# deepcool-lm's config, same format
LEGACY_CONFIG_PATH = '/etc/deepcool-lm/config.json'

SOCKET_PATH = os.environ.get('DEEPCOOL_LCD_SOCKET', '/run/deepcool-lcd/deepcool-lcd.sock')
