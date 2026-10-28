"""quickswap - switch a shared monitor and Logitech Bluetooth keyboard/mouse to another computer.

usage:
  quickswap [TARGET]        switch to TARGET (default: `default` from the config)
  quickswap status          read-only: configured monitor and devices as seen from here
  quickswap discover        read-only: every monitor and Logitech Bluetooth device, with ids for the config
  quickswap init [--force]  write a starter config, pre-filled with what discover finds
  quickswap config          print the config file path
"""
import sys

from . import __version__
from . import config as cfg
from .ddc import DdcError, backend


def _monitors(match: str | None) -> list[str]:
    try:
        ddc = backend()
        found = ddc.monitors()
    except DdcError as e:
        return [f"  ({e})"]
    if not found:
        return ["  (none visible from here)"]
    return [f"  {'[x]' if match and ddc.matches(m, match) else '[ ]'} {m[1]}  {m[0]}" for m in found]


def _logitech() -> list[tuple[int, str, int, int]]:
    """(pid, name, profiles, current) for every Logitech Bluetooth device. Unreadable ones get zeros."""
    from . import logitech
    result = []
    for pid, path in logitech.bluetooth_devices():
        try:
            with logitech.Device(path) as d:
                result.append((pid, d.name(), *d.host_info()))
        except Exception as e:
            result.append((pid, f"(unreadable: {e})", 0, 0))
    return result


def switch(config: cfg.Config, name: str) -> int:
    target = config.targets[name]
    ok = True

    if target.input is not None:
        try:
            n = backend().set_input(config.monitor_match, target.input)
        except DdcError as e:
            print(f"-> monitor: {e}", file=sys.stderr)
            n = 0
        else:
            print(f"-> monitor: {name} (input {target.input})" if n else
                  f"-> monitor: nothing matching '{config.monitor_match}' took the command (see: quickswap status)")
        ok = n > 0

    if any(d.profile_for(target) for d in config.devices):
        from . import logitech
        for device in config.devices:
            profile = device.profile_for(target)
            if profile is None:
                continue
            path = logitech.find(device.pid)
            if path is None:
                # Already on another computer; only that one can send it back.
                print(f"-> {device.name}: not connected here, skipped")
                continue
            try:
                with logitech.Device(path) as d:
                    d.set_host(profile)
                print(f"-> {device.name}: profile {profile}")
            except Exception as e:
                print(f"-> {device.name}: failed ({e})", file=sys.stderr)
                ok = False
    return 0 if ok else 1


def status(config: cfg.Config) -> int:
    print(f"config: {config.path}")
    print(f"monitors ([x] = matches '{config.monitor_match}'):")
    print("\n".join(_monitors(config.monitor_match)))
    if config.devices:
        connected = {pid: (name, current) for pid, name, _, current in _logitech()}
        print("logitech devices:")
        for d in config.devices:
            if d.pid in connected:
                print(f"  {d.name} ({d.pid:#06x}): connected here, profile {connected[d.pid][1]}")
            else:
                print(f"  {d.name} ({d.pid:#06x}): not connected here")
    print("targets:")
    for t in config.targets.values():
        mark = " (default)" if t.name == config.default else ""
        print(f"  {t.name}{mark}: input {t.input if t.input is not None else '-'}, "
              f"profile {t.profile if t.profile is not None else '-'}")
    return 0


def discover() -> int:
    print("monitors (use part of the name or id as [monitor] match):")
    print("\n".join(_monitors(None)))
    print("logitech bluetooth devices (use pid in [[logitech]]):")
    devices = _logitech()
    if not devices:
        print("  (none - devices behind a USB receiver aren't supported)")
    for pid, name, profiles, current in devices:
        print(f"  pid = 0x{pid:04X}  {name}" + (f"  ({profiles} profiles, now on {current})" if profiles else ""))
    return 0


def init(force: bool) -> int:
    path = cfg.config_path()
    if path.exists() and not force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    try:
        ddc = backend()
        found = ddc.monitors()
    except DdcError:
        found = []
    # Pre-fill the monitor only when there's no ambiguity.
    match = None
    if len(found) == 1:
        mid, desc = found[0]
        match = mid.split("\\")[1] if sys.platform == "win32" and mid.count("\\") >= 2 else desc
    devices = []
    for pid, name, profiles, _ in _logitech():
        if profiles:
            slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or f"{pid:04x}"
            devices.append((slug, pid))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg.template(match, devices), encoding="utf-8")
    print(f"wrote {path}")
    print("check the inputs/profiles in it, then try: quickswap status")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else None

    if command in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if command in ("-V", "--version"):
        print(f"quickswap {__version__}")
        return 0
    if command == "config":
        print(cfg.config_path())
        return 0
    if command == "discover":
        return discover()
    if command == "init":
        return init(force="--force" in args[1:])

    try:
        config = cfg.load()
    except cfg.ConfigError as e:
        print(f"quickswap: {e}", file=sys.stderr)
        return 1
    if command == "status":
        return status(config)

    name = command or config.default
    if name is None:
        print(f"quickswap: no target given and no default set. Targets: {', '.join(config.targets)}",
              file=sys.stderr)
        return 1
    if name not in config.targets:
        print(f"quickswap: unknown target '{name}'. Targets: {', '.join(config.targets)}", file=sys.stderr)
        return 1
    return switch(config, name)
