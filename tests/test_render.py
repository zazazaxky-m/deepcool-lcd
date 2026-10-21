import unittest

from deepcool_lcd.config import DEFAULT_CONFIG, THEMES, merge_config
from deepcool_lcd.render import font_path, temp_color
from deepcool_lcd.themes import THEME_RENDERERS, render_frame

from .helpers import NOW, Names, sample_history, sample_info

VARIANTS = {
    'default': {},
    'fahrenheit, 12-hour, light background': {'temp_unit': 'F', 'clock_24h': False, 'background': '#f2f4f8'},
    'custom colors and names, GPU focus': {'cpu_color': '#ff5c8a', 'gpu_color': '#b388ff', 'hero_focus': 'gpu',
                                           'cpu_label': 'A very long CPU label', 'gpu_label': 'GPU'},
}


class RenderTest(unittest.TestCase):
    def test_every_theme_and_variant(self):
        info, history = sample_info(), sample_history()
        for theme in THEMES:
            for name, extra in VARIANTS.items():
                with self.subTest(theme=theme, variant=name):
                    config = merge_config(DEFAULT_CONFIG, dict(extra, theme=theme))
                    img = render_frame(info, history, config, Names(), NOW)
                    self.assertEqual(img.size, (320, 240))
                    self.assertEqual(img.mode, 'RGB')
                    self.assertGreater(len(img.getcolors(320 * 240)), 20, 'the screen should not be blank')

    def test_preview_scale(self):
        config = merge_config(DEFAULT_CONFIG, {'theme': 'dashboard'})
        img = render_frame(sample_info(), sample_history(), config, Names(), NOW, scale=2)
        self.assertEqual(img.size, (640, 480))

    def test_missing_and_extreme_readings(self):
        cases = {
            'no history yet': (sample_info(), {k: [] for k in sample_history()}),
            'one point': (sample_info(), {k: v[-1:] for k, v in sample_history().items()}),
            'no GPU, no power, no cores': (sample_info(gpu_name='', gpu_temp=0.0, gpu_util=0.0, gpu_clock=0.0,
                                                       gpu_power=0.0, vram_total=0.0, cpu_power=0.0, cpu_cores=[]),
                                           sample_history()),
            'everything at the limit': (sample_info(cpu_temp=105, gpu_temp=99, cpu_percent=100, gpu_util=100,
                                                    cpu_power=250, gpu_power=600, cpu_cores=[100] * 64),
                                        sample_history(points=370, interval=0.5)),
        }
        for theme in THEMES:
            for name, (info, history) in cases.items():
                with self.subTest(theme=theme, case=name):
                    config = merge_config(DEFAULT_CONFIG, {'theme': theme})
                    self.assertEqual(render_frame(info, history, config, Names(), NOW).size, (320, 240))

    def test_deterministic(self):
        config = merge_config(DEFAULT_CONFIG, {'theme': 'aurora'})
        a = render_frame(sample_info(), sample_history(), config, Names(), NOW)
        b = render_frame(sample_info(), sample_history(), config, Names(), NOW)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_registry_and_helpers(self):
        self.assertEqual(set(THEME_RENDERERS), set(THEMES))
        self.assertEqual(len(THEMES), 15)
        self.assertEqual(temp_color(0), temp_color(30))
        self.assertNotEqual(temp_color(40), temp_color(85))
        self.assertTrue(font_path('Bold').endswith('FiraSans-Bold.ttf'), 'bundled fonts should be found')


if __name__ == '__main__':
    unittest.main()
