import base64
import io
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from deepcool_lcd import paths
from deepcool_lcd.config import DEFAULT_CONFIG
from deepcool_lcd.daemon import DisplayState, IPCServer
from deepcool_lcd.ipc import ServiceNotRunning, image_command, request

from .helpers import FakeDevice, FakeMonitor


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        # sun_path is limited to 108 bytes
        cwd = os.getcwd()
        os.chdir(self.dir.name)
        self.addCleanup(os.chdir, cwd)
        patcher = mock.patch.multiple(paths, SOCKET_PATH='test.sock',
                                      CONFIG_PATH=os.path.join(self.dir.name, 'config.json'),
                                      LEGACY_CONFIG_PATH=os.path.join(self.dir.name, 'none.json'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.device = FakeDevice()
        self.state = DisplayState(dict(DEFAULT_CONFIG))
        self.server = IPCServer(self.device, self.state, FakeMonitor())
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_get_config(self):
        r = request({'action': 'get_config'})
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['config'], DEFAULT_CONFIG)
        self.assertEqual(len(r['themes']), 15)
        self.assertEqual((r['mode'], r['cpu_name'], r['gpu_name']), ('monitor', 'Ryzen 7 9700X', 'RTX 5070'))

    def test_set_config_saves_and_validates(self):
        r = request({'action': 'set_config', 'config': {'theme': 'neon', 'cpu_color': '#AABBCC'}})
        self.assertEqual((r['config']['theme'], r['config']['cpu_color']), ('neon', '#aabbcc'))
        self.assertTrue(os.path.exists(paths.CONFIG_PATH))
        for bad in ({'theme': 'nope'}, {'foo': 1}, {'brightness': 5}, 'not an object'):
            with self.subTest(bad=bad):
                r = request({'action': 'set_config', 'config': bad})
                self.assertEqual(r['status'], 'error')
        self.assertEqual(self.state.get_config()['theme'], 'neon', 'a bad request must not change anything')

    def test_brightness(self):
        request({'action': 'set_config', 'config': {'brightness': 100}})  # unchanged: nothing sent
        request({'action': 'brightness_up'})  # already at the maximum
        request({'action': 'brightness_down'})
        request({'action': 'brightness_down'})
        request({'action': 'set_config', 'config': {'brightness': 35}})
        self.assertEqual(self.device.brightness, [90, 80, 35])

    def test_image_solid_and_back(self):
        r = request(image_command(self._png((800, 600), (255, 0, 0))))
        self.assertEqual((r['status'], r['mode']), ('ok', 'image'))
        frame = Image.open(io.BytesIO(base64.b64decode(request({'action': 'frame'})['png'])))
        self.assertEqual(frame.getpixel((10, 10)), (255, 0, 0))

        request({'action': 'set_config', 'config': {'brightness': 50, 'interval': 1}})
        self.assertEqual(self.state.get_state()[0], 'image')
        r = request({'action': 'solid', 'color': [0, 0, 255]})
        self.assertEqual(r['mode'], 'solid')
        request({'action': 'set_config', 'config': {'theme': 'rings'}})
        self.assertEqual(self.state.get_state()[0], 'monitor')

        request({'action': 'solid', 'color': [0, 0, 0]})
        self.assertEqual(request({'action': 'monitor'})['mode'], 'monitor')

    def test_rejects_bad_static_content(self):
        bad = [{'action': 'image', 'rgb': base64.b64encode(b'too short').decode()},
               {'action': 'image', 'rgb': '!!not base64!!'},
               {'action': 'image', 'data': 'files are not accepted'},
               {'action': 'solid', 'color': [0, 0, 256]},
               {'action': 'solid', 'color': 'red'},
               {'action': 'nope'}]
        for cmd in bad:
            with self.subTest(cmd=cmd):
                self.assertEqual(request(cmd)['status'], 'error')

    def test_frames(self):
        r = request({'action': 'frame', 'scale': 2})
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(r['png']))).size, (640, 480))
        thumb = request({'action': 'frame', 'config': {'theme': 'clock'}})
        self.assertEqual(thumb['status'], 'ok')
        self.assertEqual(self.state.get_config()['theme'], 'gauge', 'a preview must not change the settings')

    def test_reset(self):
        request({'action': 'set_config', 'config': {'theme': 'neon', 'brightness': 40}})
        r = request({'action': 'reset_config'})
        self.assertEqual(r['config'], DEFAULT_CONFIG)
        self.assertEqual(self.device.brightness, [40, 100])

    def test_many_clients_at_once(self):
        import threading
        results = []
        threads = [threading.Thread(target=lambda: results.append(request({'action': 'frame'})['status']))
                   for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, ['ok'] * 20)

    def test_not_running(self):
        self.server.stop()
        with self.assertRaises(ServiceNotRunning):
            request({'action': 'get_config'})

    @staticmethod
    def _png(size, color):
        buf = io.BytesIO()
        Image.new('RGB', size, color).save(buf, 'PNG')
        return buf.getvalue()


class DisplayStateTest(unittest.TestCase):
    def test_wait_wakes_on_change(self):
        import time
        state = DisplayState(dict(DEFAULT_CONFIG))
        state.set_monitor_mode()
        start = time.monotonic()
        state.wait(5)
        self.assertLess(time.monotonic() - start, 1)


if __name__ == '__main__':
    unittest.main()
