import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from deepcool_lcd import cli, paths
from deepcool_lcd.config import DEFAULT_CONFIG
from deepcool_lcd.daemon import DisplayState, IPCServer

from .helpers import FakeDevice, FakeMonitor


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        cwd = os.getcwd()
        os.chdir(self.dir.name)
        self.addCleanup(os.chdir, cwd)
        patcher = mock.patch.multiple(paths, SOCKET_PATH='cli.sock',
                                      CONFIG_PATH=os.path.join(self.dir.name, 'config.json'),
                                      LEGACY_CONFIG_PATH=os.path.join(self.dir.name, 'none.json'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.device = FakeDevice()
        self.state = DisplayState(dict(DEFAULT_CONFIG))
        self.server = IPCServer(self.device, self.state, FakeMonitor())
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_status(self):
        code, out, _ = run('status')
        self.assertEqual(code, 0)
        self.assertIn('system monitor', out)
        self.assertIn('Ryzen 7 9700X / RTX 5070', out)

    def test_theme_list_and_switch(self):
        code, out, _ = run('theme')
        self.assertEqual(code, 0)
        self.assertIn('* gauge', out)
        self.assertEqual(run('theme', 'neon')[0], 0)
        self.assertEqual(self.state.get_config()['theme'], 'neon')

    def test_settings(self):
        self.assertEqual(run('brightness', '60')[0], 0)
        self.assertEqual(run('brightness', 'down')[0], 0)
        self.assertEqual(self.device.brightness, [60, 50])
        self.assertEqual(run('interval', '0.5')[0], 0)
        self.assertEqual(run('set', 'cpu_color=#FF5C8A', 'clock_24h=false', 'cpu_label=My CPU')[0], 0)
        config = self.state.get_config()
        self.assertEqual((config['interval'], config['cpu_color'], config['clock_24h'], config['cpu_label']),
                         (0.5, '#ff5c8a', False, 'My CPU'))
        code, _, err = run('set', 'brightness=5')
        self.assertEqual(code, 1)
        self.assertIn('brightness', err)
        self.assertEqual(run('reset')[0], 0)
        self.assertEqual(self.state.get_config(), DEFAULT_CONFIG)

    def test_image_solid_monitor(self):
        picture = os.path.join(self.dir.name, 'pic.png')
        Image.new('RGB', (100, 50), (0, 255, 0)).save(picture)
        self.assertEqual(run('image', picture)[0], 0)
        self.assertEqual(self.state.get_state()[0], 'image')
        self.assertEqual(run('solid', '#000000')[0], 0)
        self.assertEqual(self.state.get_state()[0], 'solid')
        self.assertEqual(run('monitor')[0], 0)
        self.assertEqual(self.state.get_state()[0], 'monitor')
        code, _, err = run('image', os.path.join(self.dir.name, 'missing.png'))
        self.assertEqual(code, 1)
        self.assertIn("Can't open", err)

    def test_service_not_running(self):
        self.server.stop()
        code, _, err = run('status')
        self.assertEqual(code, 1)
        self.assertIn('systemctl enable --now deepcool-lcd', err)

    def test_bad_arguments(self):
        for argv in (('brightness', '5'), ('interval', '7'), ('theme', 'nope'), ('solid', 'red'), ('set', 'x=1')):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli.main(list(argv))


if __name__ == '__main__':
    unittest.main()
