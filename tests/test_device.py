import random
import unittest

from PIL import Image

from deepcool_lcd import device


class PacketTest(unittest.TestCase):
    # from deepcool-lm
    KNOWN = {
        'aa040006036100d246': bytes([0x06, 0x03, 97, 0]),     # brightness 97 ("bright")
        'aa040006031d00e60b': bytes([0x06, 0x03, 29, 0]),     # brightness 29 ("dim")
        'aa0100092991': bytes([0x09]),                        # init
        'aa040003000000dc9b': bytes([0x03, 0, 0, 0]),         # zen mode toggle
        'aa080000010058020' '02c01bc11': bytes.fromhex('0001005802002c01'),  # frame header
    }

    def test_builder_reproduces_known_packets(self):
        for packet, payload in self.KNOWN.items():
            with self.subTest(packet=packet):
                self.assertEqual(device.build_packet(payload).hex(), packet)

    def test_constants(self):
        self.assertEqual(device.INIT.hex(), 'aa0100092991')
        self.assertEqual(device.ZEN_TOGGLE.hex(), 'aa040003000000dc9b')
        self.assertEqual(device.FRAME_HEADER.hex(), 'aa08000001005802002c01bc11')
        self.assertEqual(device.brightness_packet(97).hex(), 'aa040006036100d246')
        self.assertEqual(device.brightness_packet(60).hex(), 'aa040006033c00313e')


class FramebufferTest(unittest.TestCase):
    @staticmethod
    def reference(img):
        raw, out = img.tobytes(), bytearray()
        for i in range(0, len(raw), 3):
            r, g, b = raw[i:i + 3]
            out += ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)).to_bytes(2, 'little')
        return bytes(out)

    def test_matches_reference_rgb565(self):
        rng = random.Random(1)
        img = Image.frombytes('RGB', (device.WIDTH, device.HEIGHT),
                              bytes(rng.randrange(256) for _ in range(device.WIDTH * device.HEIGHT * 3)))
        framebuffer = device.rgb_to_framebuffer(img)
        self.assertEqual(len(framebuffer), device.FRAME_BYTES)
        self.assertEqual(framebuffer, self.reference(img))

    def test_fits_other_sizes_and_modes(self):
        img = Image.new('RGBA', (800, 600), (255, 0, 0, 128))
        self.assertEqual(len(device.rgb_to_framebuffer(img)), device.FRAME_BYTES)
        self.assertEqual(device.fit_image(img).size, (device.WIDTH, device.HEIGHT))


if __name__ == '__main__':
    unittest.main()
