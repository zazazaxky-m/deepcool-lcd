import os
import tempfile
import time
import unittest
from unittest import mock

from deepcool_lcd import sensors


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class FakeSysfsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.hwmon = os.path.join(self.dir.name, 'hwmon')
        self.powercap = os.path.join(self.dir.name, 'powercap')
        patcher = mock.patch.multiple(sensors, HWMON_ROOT=self.hwmon, POWERCAP_ROOT=self.powercap)
        patcher.start()
        self.addCleanup(patcher.stop)

    def chip(self, n, name, temps):
        base = f'{self.hwmon}/hwmon{n}'
        write(f'{base}/name', name + '\n')
        for i, (label, millidegrees) in enumerate(temps, start=1):
            write(f'{base}/temp{i}_input', f'{millidegrees}\n')
            if label:
                write(f'{base}/temp{i}_label', label + '\n')
        return base

    def test_amd_cpu_uses_tctl(self):
        self.chip(0, 'nvme', [('Composite', 38000)])
        base = self.chip(2, 'k10temp', [('Tccd1', 41000), ('Tctl', 52375)])
        path = sensors.find_cpu_temp_input()
        self.assertEqual(path, f'{base}/temp2_input')
        self.assertAlmostEqual(sensors.read_sysfs_number(path) / 1000, 52.375)

    def test_intel_cpu_uses_package(self):
        base = self.chip(1, 'coretemp', [('Core 0', 40000), ('Package id 0', 55000)])
        self.assertEqual(sensors.find_cpu_temp_input(), f'{base}/temp2_input')

    def test_unlabelled_chip_uses_first_input_in_numeric_order(self):
        base = self.chip(3, 'zenpower', [(None, 1)] * 10 + [(None, 2)])
        self.assertEqual(sensors.find_cpu_temp_input(), f'{base}/temp1_input')

    def test_no_cpu_sensor(self):
        self.chip(0, 'acpitz', [(None, 16800)])
        self.assertIsNone(sensors.find_cpu_temp_input())

    def test_amdgpu(self):
        base = self.chip(6, 'amdgpu', [('edge', 61000)])
        write(f'{base}/device/gpu_busy_percent', '42\n')
        write(f'{base}/freq1_input', '2400000000\n')
        write(f'{base}/power1_average', '180000000\n')
        write(f'{base}/device/mem_info_vram_used', str(4 * 2**30))
        write(f'{base}/device/mem_info_vram_total', str(16 * 2**30))
        info = sensors.amdgpu_info(base)
        self.assertEqual((info['gpu_temp'], info['gpu_util'], info['gpu_clock'], info['gpu_power']), (61, 42, 2.4, 180))
        self.assertEqual((info['vram_used'], info['vram_total']), (4, 16))

    def test_cpu_power_meter_and_wraparound(self):
        zone = f'{self.powercap}/intel-rapl:0'
        write(f'{zone}/name', 'package-0\n')
        write(f'{zone}/max_energy_range_uj', '1000000000\n')
        write(f'{zone}/energy_uj', '999000000\n')
        meter = sensors.CpuPowerMeter()
        meter.last = (999_000_000, time.monotonic() - 1.0)  # one second ago
        write(f'{zone}/energy_uj', '49000000\n')  # wrapped: 50 J later
        self.assertAlmostEqual(meter.read(), 50, delta=2)

    def test_cpu_power_unavailable(self):
        self.assertEqual(sensors.CpuPowerMeter().read(), 0.0)


class NamesTest(unittest.TestCase):
    def test_shorten(self):
        self.assertEqual(sensors.shorten_cpu_name('AMD Ryzen 7 9700X 8-Core Processor'), 'Ryzen 7 9700X')
        self.assertEqual(sensors.shorten_cpu_name('13th Gen Intel(R) Core(TM) i7-13700K'), 'Core i7-13700K')
        self.assertEqual(sensors.shorten_cpu_name('Intel(R) Core(TM) i5-8400 CPU @ 2.80GHz'), 'Core i5-8400')
        self.assertEqual(sensors.shorten_gpu_name('NVIDIA GeForce RTX 5070'), 'RTX 5070')
        self.assertEqual(sensors.shorten_gpu_name('AMD Radeon RX 7800 XT'), 'Radeon RX 7800 XT')


class MonitorTest(unittest.TestCase):
    def test_sample_and_history_window(self):
        monitor = sensors.SystemMonitor()
        info = monitor.sample()
        for key in ('cpu_temp', 'cpu_percent', 'cpu_freq', 'gpu_temp', 'ram_used', 'cpu_power', 'time'):
            self.assertIn(key, info)
        now = time.time()
        with monitor.lock:
            for values in monitor.history.values():
                values.clear()
            for i in range(720):  # six minutes of samples every 0.5 s
                for key, values in monitor.history.items():
                    values.append(now - (720 - i) * 0.5 if key == 'time' else float(i))
        _, history = monitor.snapshot()
        span = history['time'][-1] - history['time'][0]
        self.assertLessEqual(span, sensors.SystemMonitor.HISTORY_SECONDS)
        self.assertGreater(span, sensors.SystemMonitor.HISTORY_SECONDS - 5)


if __name__ == '__main__':
    unittest.main()
