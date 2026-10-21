# Changelog

## 1.0.0 (2026-10-21)

First release. DeepCool LCD started from the [deepcool-lm](https://github.com/daedlock/deepcool-lm)
driver by dlock and adds:

- **Correct readings on AMD and Intel**: CPU temperature from `k10temp`, `zenpower` or `coretemp`
  (the original read only Intel's sensor, and showed the NVMe SSD as "GPU").
- **NVIDIA and AMD GPU stats**: temperature, load, clock, power and VRAM (NVML, `nvidia-smi` or `amdgpu`).
- **CPU power** from the RAPL energy counter, fastest-core clock, per-thread load, RAM.
- **15 layouts**: Gauge, Big Number, Dashboard, Minimal, Rings, Speedometer, Tiles, Cores, Timeline,
  Split, Aurora, Neon, Thermometer, Clock and Terminal, with custom colors, °C/°F and 12/24-hour clock.
- **Brightness from 10 to 100%** (the original had two levels), worked out from the packet checksum.
- **Refresh interval** of 0.5, 1, 2, 3, 4 or 5 seconds; graphs always cover 3 minutes.
- **DeepCool LCD Studio**, a GTK 4 app with live preview, layout gallery and all settings.
- **`deepcool-lcd` command line**: status, theme, brightness, interval, set, image, solid, preview.
- **Safer service**: runs as its own unprivileged user with systemd sandboxing; pictures are decoded
  by the client, never by the service.
- **Lighter**: about half the CPU time per frame of the first versions (no `nvidia-smi` process per
  frame, one sysfs read for the CPU temperature).
- Packages for Arch (AUR), Debian/Ubuntu (.deb) and Fedora/openSUSE (.rpm), and an installer for
  other systemd distros.
