import json
import os
import tempfile
import unittest
from unittest import mock

from deepcool_lcd import config, paths
from deepcool_lcd.config import DEFAULT_CONFIG, merge_config, validate_value


class ValidateTest(unittest.TestCase):
    def test_accepts_and_normalizes_good_values(self):
        self.assertEqual(validate_value('cpu_color', '#AABBCC'), '#aabbcc')
        self.assertEqual(validate_value('cpu_label', '  My CPU  '), 'My CPU')
        self.assertEqual(validate_value('brightness', 60.0), 60)
        self.assertEqual(validate_value('interval', 2.0), 2)
        self.assertEqual(validate_value('interval', 0.5), 0.5)
        for theme in config.THEMES:
            self.assertEqual(validate_value('theme', theme), theme)

    def test_rejects_bad_values(self):
        bad = [('theme', 'nope'), ('cpu_color', 'red'), ('cpu_color', '#12345'), ('temp_unit', 'K'),
               ('clock_24h', 'yes'), ('clock_24h', 1), ('cpu_label', 'x' * 25), ('cpu_label', 'a\nb'),
               ('hero_focus', 'ram'), ('brightness', 5), ('brightness', 101), ('brightness', True),
               ('brightness', 50.5), ('interval', 0.7), ('interval', '1'), ('interval', True), ('interval', 10)]
        for key, value in bad:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_value(key, value)

    def test_merge(self):
        merged = merge_config(DEFAULT_CONFIG, {'theme': 'neon', 'brightness': 40})
        self.assertEqual((merged['theme'], merged['brightness']), ('neon', 40))
        self.assertEqual(DEFAULT_CONFIG['theme'], 'gauge', 'defaults must not change')
        with self.assertRaises(ValueError):
            merge_config(DEFAULT_CONFIG, {'unknown': 1})
        with mock.patch('sys.stderr'):
            lenient = merge_config(DEFAULT_CONFIG, {'theme': 'nope', 'unknown': 1, 'gpu_color': '#123456'}, strict=False)
        self.assertEqual((lenient['theme'], lenient['gpu_color']), ('gauge', '#123456'))


class FileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        patcher = mock.patch.multiple(paths, CONFIG_PATH=os.path.join(self.dir.name, 'new', 'config.json'),
                                      LEGACY_CONFIG_PATH=os.path.join(self.dir.name, 'legacy.json'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def test_defaults_when_missing(self):
        self.assertEqual(config.load_config(), DEFAULT_CONFIG)

    def test_round_trip(self):
        saved = merge_config(DEFAULT_CONFIG, {'theme': 'rings', 'interval': 0.5})
        config.save_config(saved)
        self.assertEqual(config.load_config(), saved)
        self.assertEqual(os.stat(paths.CONFIG_PATH).st_mode & 0o777, 0o644)

    def test_reads_legacy_deepcool_lm_settings(self):
        with open(paths.LEGACY_CONFIG_PATH, 'w') as f:
            json.dump({'theme': 'cores', 'interval': 1, 'brightness': 70}, f)
        loaded = config.load_config()
        self.assertEqual((loaded['theme'], loaded['interval'], loaded['brightness']), ('cores', 1, 70))

    def test_broken_file_falls_back_to_defaults(self):
        os.makedirs(os.path.dirname(paths.CONFIG_PATH))
        with open(paths.CONFIG_PATH, 'w') as f:
            f.write('not json')
        with mock.patch('sys.stderr'):
            self.assertEqual(config.load_config(), DEFAULT_CONFIG)


if __name__ == '__main__':
    unittest.main()
