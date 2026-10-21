# DeepCool LM-series LCD protocol

What DeepCool LCD knows about the USB protocol of the LM-series LCD (tested on the LM360).
Corrections and captures from other models are very welcome.

## Device

| | |
|---|---|
| USB ID | `3633:0026` ("DC LM-Series") |
| Interface | 0, vendor-specific class (`0xff`), no kernel driver binds to it |
| Endpoint | bulk OUT `0x01` |
| Screen | 320 × 240, RGB565 little-endian, 153 600 bytes per frame |

## Packets

Every command is one packet:

```
0xaa | length (2 bytes, little-endian) | payload (length bytes) | CRC (2 bytes, little-endian)
```

The CRC is **CRC-16/XMODEM** of the payload (polynomial `0x1021`, initial value `0`, no
reflection, no final XOR). It was identified by checking all CRC-16 variants against the five
packets captured by the original [deepcool-lm](https://github.com/daedlock/deepcool-lm) driver;
only this one matches all of them.

```python
def crc16_xmodem(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc
```

## Commands

| Command | Payload | Full packet |
|---|---|---|
| Init / query | `09` | `aa 01 00 09 29 91` |
| Brightness | `06 03` + level (LE16) | level 97: `aa 04 00 06 03 61 00 d2 46` |
| Zen mode (screen on/off) toggle | `03 00 00 00` | `aa 04 00 03 00 00 00 dc 9b` |
| Frame header | `00 01` + frame size (LE32) + `2c 01` | `aa 08 00 00 01 00 58 02 00 2c 01 bc 11` |

**Brightness**: the captured "bright" and "dim" commands were levels 97 and 29. DeepCool LCD
sends any level from 10 to 100.

**Frames**: send the frame header packet, then the 153 600-byte framebuffer as one bulk write.
The meaning of the trailing `2c 01` (300) in the header is unknown. Each pixel is RGB565 stored
little-endian (`GGGBBBBB RRRRRGGG`).

## Service socket

The `deepcool-lcd` service listens on `/run/deepcool-lcd/deepcool-lcd.sock`. Each connection
carries one JSON request (the client then shuts down its write side) and one JSON reply, which
always has `"status": "ok"` or `"status": "error"` with a `"message"`.

| `action` | Fields | Reply |
|---|---|---|
| `get_config` | | `config`, `defaults`, `themes`, `theme_names`, `focus_themes`, `mode`, `cpu_name`, `gpu_name`, `version` |
| `set_config` | `config`: settings to change | `config`, `mode` |
| `reset_config` | | `config`, `mode` |
| `brightness_up` / `brightness_down` | | `config` (steps of 10%) |
| `image` | `rgb`: base64 of 320×240 RGB pixels (230 400 bytes) | `mode` |
| `solid` | `color`: `[r, g, b]` | `mode` |
| `monitor` | | `mode` |
| `frame` | `scale` (1–4), optional `config` overrides | `png` (base64): what the LCD shows, or the monitor screen with those overrides |

The service never decodes image files: clients convert pictures to raw pixels first.
