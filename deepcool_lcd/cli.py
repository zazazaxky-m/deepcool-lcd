import argparse
import json
import signal
import sys
import time

from . import __version__
from .config import (BRIGHTNESS_MAX, BRIGHTNESS_MIN, DEFAULT_CONFIG, HEX_COLOR, INTERVALS, THEME_NAMES, THEMES,
                     load_config, merge_config)
from .ipc import ServiceNotRunning, image_command, request

EXAMPLES = """
examples:
  deepcool-lcd status                  what the LCD is showing and its settings
  deepcool-lcd theme                   list the layouts
  deepcool-lcd theme neon              switch layout
  deepcool-lcd brightness 60           set the backlight to 60%
  deepcool-lcd interval 1              refresh every second
  deepcool-lcd set cpu_color=#ff5c8a temp_unit=F
  deepcool-lcd image ~/wallpaper.png   show a picture (deepcool-lcd monitor goes back)
  deepcool-lcd preview out.png --theme rings --scale 2
  deepcool-lcd-studio                  customize everything in a window
"""

NOT_RUNNING = ("The deepcool-lcd service isn't running. Start it with:\n"
               "  sudo systemctl enable --now deepcool-lcd")


class CommandError(Exception):
    pass


def call(cmd):
    try:
        response = request(cmd)
    except ServiceNotRunning:
        raise CommandError(NOT_RUNNING)
    except OSError as e:
        raise CommandError(f"Can't reach the deepcool-lcd service: {e}")
    if response.get('status') != 'ok':
        raise CommandError(response.get('message', 'unknown error'))
    return response


def parse_brightness(value):
    if value in ('up', 'down'):
        return value
    try:
        level = int(value)
    except ValueError:
        level = None
    if level is None or not BRIGHTNESS_MIN <= level <= BRIGHTNESS_MAX:
        raise argparse.ArgumentTypeError(f"use up, down or a number from {BRIGHTNESS_MIN} to {BRIGHTNESS_MAX}")
    return level


def parse_setting(text):
    key, sep, value = text.partition('=')
    if not sep or key not in DEFAULT_CONFIG:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE with KEY one of: {', '.join(DEFAULT_CONFIG)}")
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, (bool, int, float)):
            parsed = value
    except ValueError:
        parsed = value
    return key, parsed


def parse_color(text):
    if not HEX_COLOR.match(text):
        raise argparse.ArgumentTypeError('use a color like #000000')
    return [int(text[i:i + 2], 16) for i in (1, 3, 5)]


def show_status(response):
    config = response['config']
    mode = {'monitor': 'system monitor', 'image': 'an image', 'solid': 'a solid color'}.get(response['mode'])
    unit = '°F' if config['temp_unit'] == 'F' else '°C'
    print(f"deepcool-lcd {response['version']}, the LCD is showing {mode}")
    print(f"  layout       {THEME_NAMES.get(config['theme'], config['theme'])} ({config['theme']})")
    print(f"  brightness   {config['brightness']}%")
    print(f"  refresh      every {config['interval']} s")
    print(f"  colors       cpu {config['cpu_color']}, gpu {config['gpu_color']}, background {config['background']}")
    print(f"  display      {unit}, {'24' if config['clock_24h'] else '12'}-hour clock")
    print(f"  devices      {config['cpu_label'] or response['cpu_name']} / {config['gpu_label'] or response['gpu_name']}")


def cmd_theme(args):
    if args.name:
        call({'action': 'set_config', 'config': {'theme': args.name}})
        print(f"Layout: {THEME_NAMES[args.name]}")
        return
    try:
        current = call({'action': 'get_config'})['config']['theme']
    except CommandError:
        current = None
    for key in THEMES:
        print(f"{'*' if key == current else ' '} {key:10s} {THEME_NAMES[key]}")


def cmd_preview(args):
    from .sensors import SystemMonitor
    from .themes import render_frame
    monitor = SystemMonitor()
    time.sleep(1)
    monitor.sample()
    config = load_config()
    if args.theme:
        config['theme'] = args.theme
    info, history = monitor.snapshot()
    render_frame(info, history, config, monitor, scale=args.scale).save(args.output)
    print(f"Saved the {THEME_NAMES[config['theme']]} layout to {args.output}")


def cmd_daemon(args):
    from .daemon import run
    from .device import DeviceError
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        run(args.interval)
    except DeviceError as e:
        print(f"deepcool-lcd: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='deepcool-lcd', description='Custom screens for DeepCool LM-series AIO cooler LCDs.',
        epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')

    p = sub.add_parser('daemon', help='run the service that drives the LCD (started by systemd)')
    p.add_argument('--interval', type=float, choices=INTERVALS, metavar='SECONDS',
                   help='refresh interval for this run: 0.5, 1, 2, 3, 4 or 5')
    sub.add_parser('status', help='show what the LCD is doing and its settings')
    p = sub.add_parser('theme', help='list the layouts, or switch to one')
    p.add_argument('name', nargs='?', choices=THEMES, metavar='NAME', help=', '.join(THEMES))
    p = sub.add_parser('brightness', help='set the backlight: up / down by 10%%, or 10-100')
    p.add_argument('level', type=parse_brightness, metavar='up|down|10-100')
    p = sub.add_parser('interval', help='seconds between refreshes: 0.5, 1, 2, 3, 4 or 5')
    p.add_argument('seconds', type=float, choices=INTERVALS, metavar='SECONDS')
    p = sub.add_parser('set', help='change settings, e.g. set cpu_color=#ff5c8a clock_24h=false')
    p.add_argument('settings', type=parse_setting, nargs='+', metavar='KEY=VALUE')
    sub.add_parser('reset', help='restore the default settings')
    p = sub.add_parser('image', help='show a picture (resized to 320x240)')
    p.add_argument('path')
    p = sub.add_parser('solid', help='show a solid color, e.g. solid "#000000"')
    p.add_argument('color', type=parse_color, metavar='#RRGGBB')
    sub.add_parser('monitor', help='go back to the system monitor')
    p = sub.add_parser('preview', help='render a layout to a PNG with live readings (no LCD needed)')
    p.add_argument('output')
    p.add_argument('--theme', choices=THEMES, metavar='NAME', help='layout to render (default: the saved one)')
    p.add_argument('--scale', type=int, default=1, choices=[1, 2, 3, 4], help='render larger, e.g. 2 for 640x480')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command is None:
            build_parser().print_help()
            return 1
        if args.command == 'daemon':
            return cmd_daemon(args)
        if args.command == 'preview':
            cmd_preview(args)
        elif args.command == 'status':
            show_status(call({'action': 'get_config'}))
        elif args.command == 'theme':
            cmd_theme(args)
        elif args.command == 'brightness':
            if args.level in ('up', 'down'):
                config = call({'action': f'brightness_{args.level}'})['config']
            else:
                config = call({'action': 'set_config', 'config': {'brightness': args.level}})['config']
            print(f"Brightness: {config['brightness']}%")
        elif args.command == 'interval':
            config = call({'action': 'set_config', 'config': {'interval': args.seconds}})['config']
            print(f"Refreshing every {config['interval']} s")
        elif args.command == 'set':
            changes = dict(args.settings)
            merge_config(DEFAULT_CONFIG, changes)
            call({'action': 'set_config', 'config': changes})
            print('Updated: ' + ', '.join(f'{k}={v}' for k, v in changes.items()))
        elif args.command == 'reset':
            call({'action': 'reset_config'})
            print('Restored the default settings')
        elif args.command == 'image':
            try:
                cmd = image_command(args.path)
            except (OSError, ValueError) as e:
                raise CommandError(f"Can't open {args.path}: {e}")
            call(cmd)
            print(f"Showing {args.path} (deepcool-lcd monitor goes back to the stats)")
        elif args.command == 'solid':
            call({'action': 'solid', 'color': args.color})
            print('Showing a solid color (deepcool-lcd monitor goes back to the stats)')
        elif args.command == 'monitor':
            call({'action': 'monitor'})
            print('Showing the system monitor')
    except (CommandError, ValueError) as e:
        print(f"deepcool-lcd: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
