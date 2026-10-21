import base64
import json
import socket
import time
from io import BytesIO

from PIL import Image

from . import paths
from .device import fit_image


class ServiceNotRunning(OSError):
    pass


def request(cmd, timeout=5, attempts=5):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        for attempt in range(attempts):
            try:
                sock.connect(paths.SOCKET_PATH)
                break
            except (FileNotFoundError, ConnectionRefusedError) as e:
                raise ServiceNotRunning(f'the deepcool-lcd service is not running ({paths.SOCKET_PATH})') from e
            except BlockingIOError:  # backlog full
                if attempt == attempts - 1:
                    raise
                time.sleep(0.15)
        sock.sendall(json.dumps(cmd).encode('utf-8'))
        sock.shutdown(socket.SHUT_WR)
        data = b''
        while chunk := sock.recv(65536):
            data += chunk
    return json.loads(data.decode('utf-8'))


def image_command(source):
    with Image.open(source if isinstance(source, str) else BytesIO(source)) as img:
        rgb = fit_image(img).tobytes()
    return {'action': 'image', 'rgb': base64.b64encode(rgb).decode('ascii')}
