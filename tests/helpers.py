import datetime
import math

NOW = datetime.datetime(2026, 10, 21, 14, 30, 12)


def sample_info(**overrides):
    info = {
        'cpu_temp': 52.4, 'cpu_percent': 23.0, 'cpu_freq': 4.62, 'cpu_freq_max': 5.58,
        'cpu_cores': [10, 35, 5, 60, 22, 8, 90, 15, 30, 12, 45, 7, 3, 70, 18, 25],
        'cpu_power': 64.7, 'ram_used': 11.2, 'ram_total': 31.3, 'ram_percent': 35.8, 'uptime': 3 * 3600 + 25 * 60,
        'gpu_name': 'NVIDIA GeForce RTX 5070', 'gpu_temp': 47.0, 'gpu_util': 31.0, 'gpu_clock': 2.31,
        'gpu_clock_max': 3.13, 'gpu_power': 96.0, 'gpu_power_limit': 250.0, 'vram_used': 3.4, 'vram_total': 11.9,
        'time': NOW.timestamp(),
    }
    info.update(overrides)
    return info


def sample_history(points=90, interval=2.0):
    end = NOW.timestamp()
    history = {k: [] for k in ('cpu_temp', 'cpu_percent', 'gpu_temp', 'gpu_util', 'time')}
    for i in range(points):
        t = i / max(points - 1, 1)
        history['cpu_temp'].append(48 + 4 * math.sin(t * 6) + 3 * t)
        history['cpu_percent'].append(max(0.0, 20 + 15 * math.sin(t * 9) + (25 if 0.6 < t < 0.7 else 0)))
        history['gpu_temp'].append(44 + 3 * math.sin(t * 4 + 1))
        history['gpu_util'].append(max(0.0, 25 + 20 * math.sin(t * 5 + 2)))
        history['time'].append(end - (points - 1 - i) * interval)
    return history


class Names:
    cpu_name = 'Ryzen 7 9700X'
    gpu_name = 'RTX 5070'


class FakeDevice:
    def __init__(self):
        self.brightness = []
        self.frames = []

    def set_brightness(self, level):
        self.brightness.append(level)

    def send_frame(self, framebuffer):
        self.frames.append(framebuffer)


class FakeMonitor(Names):
    def snapshot(self):
        return sample_info(), sample_history()
