import base64
import json
import os
import socket
import sys
import threading
import time
from io import BytesIO

from PIL import Image

from . import __version__, paths
from .config import (BRIGHTNESS_MAX, BRIGHTNESS_MIN, BRIGHTNESS_STEP, DEFAULT_CONFIG, DEVICE_SETTINGS,
                     FOCUS_THEMES, THEME_NAMES, THEMES, load_config, merge_config, save_config, validate_value)
from .device import HEIGHT, LM360, WIDTH, rgb_to_framebuffer
from .sensors import SystemMonitor
from .themes import render_frame

MAX_REQUEST_BYTES = 4 * 1024 * 1024


class DisplayState:
    def __init__(self, config):
        self.mode = 'monitor'  # 'monitor', 'image', 'solid'
        self.data = None
        self.image = None
        self.config = config
        self.lock = threading.Lock()
        self.changed = threading.Event()

    def set_monitor_mode(self):
        with self.lock:
            self.mode, self.data, self.image = 'monitor', None, None
        self.changed.set()

    def set_static(self, mode, img):
        with self.lock:
            self.mode, self.image, self.data = mode, img, rgb_to_framebuffer(img)
        self.changed.set()

    def set_config(self, config, show_monitor=True):
        with self.lock:
            self.config = config
            if show_monitor:
                self.mode, self.data, self.image = 'monitor', None, None
        self.changed.set()

    def get_state(self):
        with self.lock:
            return self.mode, self.data

    def get_config(self):
        with self.lock:
            return dict(self.config)

    def get_static_image(self):
        with self.lock:
            return self.image

    def wait(self, timeout):
        self.changed.wait(timeout)
        self.changed.clear()


class IPCServer:
    def __init__(self, device, display_state, monitor, socket_path=None):
        self.device = device
        self.display_state = display_state
        self.monitor = monitor
        self.socket_path = socket_path or paths.SOCKET_PATH
        self.running = False
        self.server_socket = None

    def start(self):
        directory = os.path.dirname(self.socket_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        # any local user may control the LCD; only JSON and raw pixels are accepted
        os.chmod(self.socket_path, 0o666)
        self.server_socket.listen(64)
        self.running = True
        threading.Thread(target=self._serve, daemon=True).start()

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

    def _serve(self):
        while self.running:
            try:
                conn, _ = self.server_socket.accept()
            except OSError:
                if self.running:
                    time.sleep(0.1)
                continue
            with conn:
                self._handle(conn)

    def _handle(self, conn):
        try:
            conn.settimeout(5)
            data = b''
            while chunk := conn.recv(65536):
                data += chunk
                if len(data) > MAX_REQUEST_BYTES:
                    raise ValueError('request too large')
            if not data:
                return
            cmd = json.loads(data.decode('utf-8'))
            if not isinstance(cmd, dict):
                raise ValueError('request must be a JSON object')
            response = self.dispatch(cmd)
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
        try:
            conn.sendall(json.dumps(response).encode('utf-8'))
        except OSError:
            pass

    def dispatch(self, cmd):
        action = cmd.get('action')
        state = self.display_state
        response = {'status': 'ok'}
        if action == 'get_config':
            response.update({
                'version': __version__,
                'config': state.get_config(),
                'defaults': DEFAULT_CONFIG,
                'themes': list(THEMES),
                'theme_names': THEME_NAMES,
                'focus_themes': list(FOCUS_THEMES),
                'mode': state.get_state()[0],
                'cpu_name': self.monitor.cpu_name,
                'gpu_name': self.monitor.gpu_name,
            })
        elif action == 'set_config':
            changes = cmd.get('config', {})
            if not isinstance(changes, dict):
                raise ValueError('config must be an object')
            response['config'] = self.update_config(changes)
        elif action == 'reset_config':
            response['config'] = self.update_config(DEFAULT_CONFIG)
        elif action in ('brightness_up', 'brightness_down'):
            step = BRIGHTNESS_STEP if action == 'brightness_up' else -BRIGHTNESS_STEP
            level = min(max(state.get_config()['brightness'] + step, BRIGHTNESS_MIN), BRIGHTNESS_MAX)
            response['config'] = self.update_config({'brightness': level})
        elif action == 'monitor':
            state.set_monitor_mode()
        elif action == 'image':
            rgb = base64.b64decode(cmd['rgb'], validate=True)
            if len(rgb) != WIDTH * HEIGHT * 3:
                raise ValueError(f'image must be {WIDTH}x{HEIGHT} RGB ({WIDTH * HEIGHT * 3} bytes)')
            state.set_static('image', Image.frombytes('RGB', (WIDTH, HEIGHT), rgb))
        elif action == 'solid':
            color = cmd.get('color')
            if (not isinstance(color, list) or len(color) != 3
                    or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in color)):
                raise ValueError('color must be [r, g, b] with values from 0 to 255')
            state.set_static('solid', Image.new('RGB', (WIDTH, HEIGHT), tuple(color)))
        elif action == 'frame':
            response.update(self.frame(cmd))
        else:
            return {'status': 'error', 'message': f'unknown action: {action}'}
        response['mode'] = state.get_state()[0]
        return response

    def frame(self, cmd):
        scale = min(max(int(cmd.get('scale', 1)), 1), 4)
        override = cmd.get('config')
        img = None if override is not None else self.display_state.get_static_image()
        if img is None:
            config = merge_config(self.display_state.get_config(), override or {})
            info, history = self.monitor.snapshot()
            img = render_frame(info, history, config, self.monitor, scale=scale)
        elif scale > 1:
            img = img.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='PNG', compress_level=1)
        return {'png': base64.b64encode(buf.getvalue()).decode('ascii')}

    def update_config(self, changes):
        old = self.display_state.get_config()
        config = merge_config(old, changes)
        save_config(config)
        if config['brightness'] != old['brightness']:
            self.device.set_brightness(config['brightness'])
        show_monitor = any(config[k] != old[k] for k in config if k not in DEVICE_SETTINGS)
        self.display_state.set_config(config, show_monitor=show_monitor)
        return config


def run(interval=None):
    config = load_config()
    if interval is not None:
        config['interval'] = validate_value('interval', interval)
    if not os.path.exists(paths.CONFIG_PATH):
        try:
            save_config(config)  # migrates deepcool-lm settings
        except OSError:
            pass

    device = LM360()
    device.connect()
    state = DisplayState(config)
    monitor = SystemMonitor()
    device.init()
    time.sleep(0.5)
    device.set_brightness(config['brightness'])

    server = IPCServer(device, state, monitor)
    server.start()
    print(f'deepcool-lcd {__version__}: driving the LCD, listening on {server.socket_path}', flush=True)
    try:
        while True:
            mode, data = state.get_state()
            if mode == 'monitor':
                info = monitor.sample()
                _, history = monitor.snapshot()
                img = render_frame(info, history, state.get_config(), monitor)
                device.send_frame(rgb_to_framebuffer(img))
            elif data:
                device.send_frame(data)
            state.wait(state.get_config()['interval'])
    finally:
        server.stop()
        device.disconnect()
        print('deepcool-lcd: stopped', file=sys.stderr, flush=True)
