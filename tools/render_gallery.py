#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from PIL import Image  # noqa: E402

from deepcool_lcd.config import DEFAULT_CONFIG, THEMES, merge_config  # noqa: E402
from deepcool_lcd.themes import render_frame  # noqa: E402
from tests.helpers import NOW, Names, sample_history, sample_info  # noqa: E402

COLUMNS, SCALE, GAP = 3, 2, 24
BACKDROP = (24, 26, 32)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    info, history = sample_info(), sample_history()
    shots = []
    for theme in THEMES:
        img = render_frame(info, history, merge_config(DEFAULT_CONFIG, {'theme': theme}), Names(), NOW, scale=SCALE)
        img.save(os.path.join(out_dir, f'{theme}.png'), optimize=True)
        shots.append(img)
    w, h = shots[0].size
    rows = (len(shots) + COLUMNS - 1) // COLUMNS
    sheet = Image.new('RGB', (COLUMNS * (w + GAP) + GAP, rows * (h + GAP) + GAP), BACKDROP)
    for i, img in enumerate(shots):
        sheet.paste(img, (GAP + (i % COLUMNS) * (w + GAP), GAP + (i // COLUMNS) * (h + GAP)))
    sheet.save(os.path.join(out_dir, 'gallery.png'), optimize=True)
    print(f'Rendered {len(shots)} layouts into {out_dir}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'docs/screenshots')
