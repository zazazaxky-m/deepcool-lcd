import ctypes
import glob
import os
import re
import subprocess
import threading
import time
from collections import deque

import psutil

from .config import INTERVALS

# overridden in tests
HWMON_ROOT = '/sys/class/hwmon'
POWERCAP_ROOT = '/sys/class/powercap'


def read_sysfs_number(path):
    try:
        with open(path) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return 0.0


def parse_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0  # nvidia-smi reports [N/A] for unsupported fields


def find_hwmon(name):
    dirs = []
    for name_file in sorted(glob.glob(f'{HWMON_ROOT}/hwmon*/name')):
        try:
            with open(name_file) as f:
                if f.read().strip() == name:
                    dirs.append(os.path.dirname(name_file))
        except OSError:
            pass
    return dirs


def find_temp_input(chip, labels):
    for hwmon in find_hwmon(chip):
        inputs = sorted(glob.glob(f'{hwmon}/temp*_input'), key=lambda p: int(re.search(r'temp(\d+)_input$', p).group(1)))
        labelled = {}
        for path in inputs:
            try:
                with open(path[:-len('_input')] + '_label') as f:
                    labelled[f.read().strip()] = path
            except OSError:
                pass
        for label in labels:
            if label in labelled:
                return labelled[label]
        if inputs:
            return inputs[0]
    return None


CPU_TEMP_SENSORS = (('coretemp', ['Package id 0']), ('k10temp', ['Tctl', 'Tdie']), ('zenpower', ['Tdie', 'Tctl']))


def find_cpu_temp_input():
    for chip, labels in CPU_TEMP_SENSORS:
        path = find_temp_input(chip, labels)
        if path:
            return path
    return None


def cpu_temp_from_psutil():
    temps = psutil.sensors_temperatures()
    for chip, labels in CPU_TEMP_SENSORS:
        entries = temps.get(chip)
        if entries:
            for label in labels:
                for entry in entries:
                    if entry.label == label:
                        return entry.current
            return entries[0].current
    return 0.0


class NvmlGpu:
    TEMPERATURE_GPU = 0
    CLOCK_GRAPHICS = 0

    class Utilization(ctypes.Structure):
        _fields_ = [('gpu', ctypes.c_uint), ('memory', ctypes.c_uint)]

    class Memory(ctypes.Structure):
        _fields_ = [('total', ctypes.c_ulonglong), ('free', ctypes.c_ulonglong), ('used', ctypes.c_ulonglong)]

    class MemoryV2(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint), ('total', ctypes.c_ulonglong), ('reserved', ctypes.c_ulonglong),
                    ('free', ctypes.c_ulonglong), ('used', ctypes.c_ulonglong)]

    def __init__(self):
        self.lib = ctypes.CDLL('libnvidia-ml.so.1')  # OSError if the driver isn't installed
        self._check(self.lib.nvmlInit_v2())
        self.handle = ctypes.c_void_p()
        self._check(self.lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.handle)))
        name = ctypes.create_string_buffer(96)
        self._check(self.lib.nvmlDeviceGetName(self.handle, name, len(name)))
        self.name = name.value.decode(errors='replace')
        self.clock_max = self._uint(self.lib.nvmlDeviceGetMaxClockInfo, self.CLOCK_GRAPHICS) / 1000
        self.power_limit = self._uint(self.lib.nvmlDeviceGetEnforcedPowerLimit) / 1000

    @staticmethod
    def _check(result):
        if result != 0:
            raise OSError(f'NVML error {result}')

    def _uint(self, fn, *args):
        value = ctypes.c_uint()
        return value.value if fn(self.handle, *args, ctypes.byref(value)) == 0 else 0

    def _memory(self):
        # v2 'used' matches nvidia-smi
        fn = getattr(self.lib, 'nvmlDeviceGetMemoryInfo_v2', None)
        mem = self.MemoryV2(version=ctypes.sizeof(self.MemoryV2) | (2 << 24))
        if fn is not None and fn(self.handle, ctypes.byref(mem)) == 0:
            return mem.used, mem.total
        mem = self.Memory()
        if self.lib.nvmlDeviceGetMemoryInfo(self.handle, ctypes.byref(mem)) == 0:
            return mem.used, mem.total
        return 0, 0

    def read(self):
        util = self.Utilization()
        self._check(self.lib.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(util)))
        used, total = self._memory()
        return {
            'gpu_name': self.name,
            'gpu_temp': float(self._uint(self.lib.nvmlDeviceGetTemperature, self.TEMPERATURE_GPU)),
            'gpu_util': float(util.gpu),
            'gpu_clock': self._uint(self.lib.nvmlDeviceGetClockInfo, self.CLOCK_GRAPHICS) / 1000,
            'gpu_clock_max': self.clock_max,
            'gpu_power': self._uint(self.lib.nvmlDeviceGetPowerUsage) / 1000,
            'gpu_power_limit': self.power_limit,
            'vram_used': used / 2**30,
            'vram_total': total / 2**30,
        }


def open_nvml():
    try:
        return NvmlGpu()
    except (OSError, AttributeError):
        return None


NVIDIA_SMI_FIELDS = ('name,temperature.gpu,utilization.gpu,clocks.gr,clocks.max.gr,power.draw,'
                     'memory.used,memory.total,power.limit')

NO_GPU = {'gpu_name': '', 'gpu_temp': 0.0, 'gpu_util': 0.0, 'gpu_clock': 0.0, 'gpu_clock_max': 0.0,
          'gpu_power': 0.0, 'gpu_power_limit': 0.0, 'vram_used': 0.0, 'vram_total': 0.0}


def nvidia_smi_info():
    result = subprocess.run(['nvidia-smi', f'--query-gpu={NVIDIA_SMI_FIELDS}', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=2)
    if result.returncode != 0:
        return None
    fields = [f.strip() for f in result.stdout.splitlines()[0].split(',')]
    return {
        'gpu_name': fields[0],
        'gpu_temp': parse_float(fields[1]),
        'gpu_util': parse_float(fields[2]),
        'gpu_clock': parse_float(fields[3]) / 1000,
        'gpu_clock_max': parse_float(fields[4]) / 1000,
        'gpu_power': parse_float(fields[5]),
        'vram_used': parse_float(fields[6]) / 1024,
        'vram_total': parse_float(fields[7]) / 1024,
        'gpu_power_limit': parse_float(fields[8]),
    }


def amdgpu_info(hwmon):
    return {
        'gpu_name': 'Radeon',
        'gpu_temp': read_sysfs_number(f'{hwmon}/temp1_input') / 1000,  # edge
        'gpu_util': read_sysfs_number(f'{hwmon}/device/gpu_busy_percent'),
        'gpu_clock': read_sysfs_number(f'{hwmon}/freq1_input') / 1e9,
        'gpu_clock_max': 0.0,
        'gpu_power': (read_sysfs_number(f'{hwmon}/power1_average') or read_sysfs_number(f'{hwmon}/power1_input')) / 1e6,
        'gpu_power_limit': read_sysfs_number(f'{hwmon}/power1_cap') / 1e6,
        'vram_used': read_sysfs_number(f'{hwmon}/device/mem_info_vram_used') / 2**30,
        'vram_total': read_sysfs_number(f'{hwmon}/device/mem_info_vram_total') / 2**30,
    }


def get_gpu_info(nvml=None, amdgpu=None):
    if nvml is not None:
        try:
            return nvml.read()
        except OSError:
            pass
    try:
        info = nvidia_smi_info()
        if info:
            return info
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    if amdgpu:
        return amdgpu_info(amdgpu)
    return dict(NO_GPU)


def shorten_cpu_name(name):
    name = re.sub(r'\(R\)|\(TM\)|\d+(st|nd|rd|th) Gen|\bAMD\b|\bIntel\b|\b\w+-Core\b|\bProcessor\b|\bCPU\b|@.*$', ' ', name)
    return ' '.join(name.split()) or 'CPU'


def shorten_gpu_name(name):
    name = re.sub(r'\bNVIDIA\b|\bGeForce\b|\bAMD\b', ' ', name)
    return ' '.join(name.split()) or 'GPU'


def detect_cpu_name():
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('model name'):
                    return shorten_cpu_name(line.split(':', 1)[1])
    except OSError:
        pass
    return 'CPU'


class CpuPowerMeter:
    def __init__(self):
        self.path = None
        self.max_range = 0
        for name_file in sorted(glob.glob(f'{POWERCAP_ROOT}/intel-rapl:*/name')):
            try:
                with open(name_file) as f:
                    if f.read().strip() != 'package-0':
                        continue
                zone = os.path.dirname(name_file)
                with open(f'{zone}/max_energy_range_uj') as f:
                    self.max_range = int(f.read())
                self.path = f'{zone}/energy_uj'
                break
            except (OSError, ValueError):
                continue
        self.last = None
        self.read()

    def read(self):
        if not self.path:
            return 0.0
        try:
            with open(self.path) as f:
                energy = int(f.read())
        except (OSError, ValueError):
            self.path = None  # not readable by this user
            return 0.0
        now = time.monotonic()
        watts = 0.0
        if self.last:
            last_energy, last_time = self.last
            delta = energy - last_energy
            if delta < 0:  # wrapped
                delta += self.max_range
            if now > last_time:
                watts = delta / (now - last_time) / 1e6
        self.last = (energy, now)
        return watts


def get_system_info(cpu_temp_input=None, nvml=None, amdgpu=None):
    info = {
        'cpu_temp': 0.0,
        'cpu_percent': 0.0,
        'cpu_freq': 0.0,
        'cpu_freq_max': 0.0,
        'cpu_cores': [],
        'ram_used': 0.0,
        'ram_total': 0.0,
        'ram_percent': 0.0,
        'uptime': 0.0,
    }
    # much cheaper than psutil.sensors_temperatures(), which also polls NVMe and WMI
    try:
        if cpu_temp_input:
            info['cpu_temp'] = round(read_sysfs_number(cpu_temp_input) / 1000, 1)
        else:
            info['cpu_temp'] = round(cpu_temp_from_psutil(), 1)
    except Exception:
        pass
    info.update(get_gpu_info(nvml, amdgpu))
    try:
        info['cpu_percent'] = round(psutil.cpu_percent(interval=None), 1)
        info['cpu_cores'] = psutil.cpu_percent(interval=None, percpu=True)
        # fastest core; idle cores drag the average down
        freqs = psutil.cpu_freq(percpu=True)
        if freqs:
            info['cpu_freq'] = round(max(f.current for f in freqs) / 1000, 2)
            info['cpu_freq_max'] = max(f.max for f in freqs) / 1000
    except Exception:
        pass
    try:
        mem = psutil.virtual_memory()
        info['ram_used'] = mem.used / 2**30
        info['ram_total'] = mem.total / 2**30
        info['ram_percent'] = mem.percent
        info['uptime'] = time.time() - psutil.boot_time()
    except Exception:
        pass
    return info


class SystemMonitor:
    HISTORY_SECONDS = 180
    HISTORY = int(HISTORY_SECONDS / min(INTERVALS)) + 10
    HISTORY_KEYS = ('cpu_temp', 'cpu_percent', 'gpu_temp', 'gpu_util', 'time')

    def __init__(self):
        self.cpu_name = detect_cpu_name()
        self.gpu_name = 'GPU'
        self.history = {k: deque(maxlen=self.HISTORY) for k in self.HISTORY_KEYS}
        self.latest = None
        self.lock = threading.Lock()
        # the first call always returns 0
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self.cpu_power = CpuPowerMeter()
        self.cpu_temp_input = find_cpu_temp_input()
        self.nvml = open_nvml()
        # prefer the dGPU
        amdgpu = find_hwmon('amdgpu')
        self.amdgpu = max(amdgpu, key=lambda h: read_sysfs_number(f'{h}/device/mem_info_vram_total')) if amdgpu else None

    def sample(self):
        info = get_system_info(self.cpu_temp_input, self.nvml, self.amdgpu)
        info['cpu_power'] = self.cpu_power.read()
        info['time'] = time.time()
        with self.lock:
            if info['gpu_name']:
                self.gpu_name = shorten_gpu_name(info['gpu_name'])
            self.latest = info
            for key, values in self.history.items():
                values.append(info[key])
        return info

    def snapshot(self):
        with self.lock:
            latest = self.latest
            cutoff = time.time() - self.HISTORY_SECONDS
            times = self.history['time']
            start = next((i for i, t in enumerate(times) if t >= cutoff), len(times))
            history = {k: list(v)[start:] for k, v in self.history.items()}
        if latest is None:
            latest = self.sample()
            history = {k: [latest[k]] for k in self.HISTORY_KEYS}
        return latest, history
