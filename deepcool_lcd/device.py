import sys
import threading

from PIL import Image, ImageChops

VENDOR_ID = 0x3633
PRODUCT_ID = 0x0026
EP_OUT = 0x01
WIDTH = 320
HEIGHT = 240
FRAME_BYTES = WIDTH * HEIGHT * 2  # RGB565


def crc16_xmodem(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_packet(payload):
    return (bytes([0xaa]) + len(payload).to_bytes(2, 'little') + payload
            + crc16_xmodem(payload).to_bytes(2, 'little'))


INIT = build_packet(bytes([0x09]))
ZEN_TOGGLE = build_packet(bytes([0x03, 0x00, 0x00, 0x00]))
# 00 01, frame size, 2c 01 (unknown)
FRAME_HEADER = build_packet(bytes([0x00, 0x01]) + FRAME_BYTES.to_bytes(4, 'little') + bytes([0x2c, 0x01]))


def brightness_packet(level):
    return build_packet(bytes([0x06, 0x03]) + int(level).to_bytes(2, 'little'))


def fit_image(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    return img


def rgb_to_framebuffer(img):
    r, g, b = fit_image(img).split()
    # low byte GGGBBBBB, high byte RRRRRGGG
    low = ImageChops.add(g.point(lambda v: ((v >> 2) & 0x07) << 5), b.point(lambda v: v >> 3))
    high = ImageChops.add(r.point(lambda v: (v >> 3) << 3), g.point(lambda v: v >> 5))
    return Image.merge('LA', (low, high)).tobytes()


class DeviceError(Exception):
    pass


class LM360:
    MAX_FAILED_WRITES = 3

    def __init__(self):
        self.dev = None
        self.interface = 0
        self.lock = threading.Lock()
        self.failed_writes = 0

    def connect(self):
        import usb.core
        import usb.util
        self.dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if self.dev is None:
            raise DeviceError('No DeepCool LM-series LCD found (USB 3633:0026). Is the cooler plugged in?')
        try:
            if self.dev.is_kernel_driver_active(self.interface):
                self.dev.detach_kernel_driver(self.interface)
            self.dev.set_configuration()
            usb.util.claim_interface(self.dev, self.interface)
        except usb.core.USBError as e:
            if e.errno == 13:
                raise DeviceError('Permission denied opening the LCD. Run it through the deepcool-lcd service, '
                                  'or check that the udev rule is installed.') from e
            if e.errno == 16:
                raise DeviceError('The LCD is busy. Is another driver (e.g. deepcool-lm) still running?') from e
            raise DeviceError(f'Could not open the LCD: {e}') from e

    def write(self, data):
        try:
            self.dev.write(EP_OUT, data, timeout=5000)
            self.failed_writes = 0
        except Exception as e:
            self.failed_writes += 1
            print(f"USB write failed: {e}", file=sys.stderr)
            if self.failed_writes >= self.MAX_FAILED_WRITES:
                raise DeviceError('Lost the connection to the LCD') from e

    def command(self, packet):
        with self.lock:
            self.write(packet)

    def send_frame(self, framebuffer):
        with self.lock:
            self.write(FRAME_HEADER)
            self.write(framebuffer)

    def init(self):
        self.command(INIT)

    def set_brightness(self, level):
        self.command(brightness_packet(level))

    def toggle_zen_mode(self):
        self.command(ZEN_TOGGLE)

    def disconnect(self):
        if self.dev:
            import usb.util
            try:
                usb.util.release_interface(self.dev, self.interface)
                usb.util.dispose_resources(self.dev)
            except Exception:
                pass
