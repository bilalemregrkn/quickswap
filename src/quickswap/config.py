"""Loading and writing the per-machine config file (TOML)."""
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Command names that can't double as target names.
RESERVED = {"status", "discover", "init", "config", "help"}


class ConfigError(Exception):
    pass


@dataclass
class Target:
    name: str
    input: int | None     # VCP 0x60 value, None = leave the monitor alone
    profile: int | None   # Easy-Switch profile 1-3, None = leave devices alone


@dataclass
class Device:
    name: str
    pid: int
    profiles: dict[str, int] = field(default_factory=dict)   # per-target overrides

    def profile_for(self, target: Target) -> int | None:
        return self.profiles.get(target.name, target.profile)


@dataclass
class Config:
    path: Path
    default: str | None
    monitor_match: str | None
    targets: dict[str, Target]
    devices: list[Device]


def config_path() -> Path:
    if env := os.environ.get("QUICKSWAP_CONFIG"):
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "quickswap" / "config.toml"


def _int(value, what, lo, hi):
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ConfigError(f"{what} must be an integer {lo}-{hi}, got {value!r}")
    return value


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(f"no config at {path} (create one with: quickswap init)")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None

    targets = {}
    for name, t in (data.get("targets") or {}).items():
        if name in RESERVED:
            raise ConfigError(f"'{name}' is a command name and can't be a target")
        targets[name] = Target(
            name,
            None if "input" not in t else _int(t["input"], f"targets.{name}.input", 0, 255),
            None if "profile" not in t else _int(t["profile"], f"targets.{name}.profile", 1, 3),
        )
    if not targets:
        raise ConfigError(f"{path}: no [targets.*] defined")

    devices = []
    for i, d in enumerate(data.get("logitech") or []):
        if "pid" not in d:
            raise ConfigError(f"logitech entry #{i + 1} has no pid (see: quickswap discover)")
        pid = _int(d["pid"], "logitech pid", 0, 0xFFFF)
        label = str(d.get("name") or f"{pid:#06x}")
        profiles = {}
        for target, p in (d.get("profiles") or {}).items():
            if target not in targets:
                raise ConfigError(f"logitech '{label}': unknown target '{target}' in profiles")
            profiles[target] = _int(p, f"logitech '{label}' profiles.{target}", 1, 3)
        devices.append(Device(label, pid, profiles))

    default = data.get("default")
    if default is not None and default not in targets:
        raise ConfigError(f"default = '{default}' is not one of the targets: {', '.join(targets)}")

    monitor_match = (data.get("monitor") or {}).get("match") or None
    if monitor_match is None and any(t.input is not None for t in targets.values()):
        raise ConfigError("targets set a monitor input but [monitor] match is empty")

    return Config(path, default, monitor_match, targets, devices)


def template(monitor_match: str | None, devices: list[tuple[str, int]]) -> str:
    """A starter config. The bare `quickswap` goes to "the other machine", so the default depends on the OS."""
    default = "win" if sys.platform == "darwin" else "mac"
    lines = [
        "# quickswap config - one per machine. Find your ids with: quickswap discover",
        "",
        "# Where a bare `quickswap` goes. Usually the *other* machine.",
        f'default = "{default}"',
        "",
        "[monitor]",
        "# Substring identifying the monitor (case-insensitive).",
        "#   macOS:   matched against the name or UUID from `m1ddc display list`",
        "#   Windows: matched against the PnP id, e.g. MONITOR\\MSI4BA4\\...",
        f'match = "{monitor_match or "CHANGE-ME"}"',
        "",
        "# One table per computer. input = the monitor port it's plugged into (VCP 0x60 value):",
        "#   15 = DisplayPort 1, 16 = DisplayPort 2, 17 = HDMI 1, 18 = HDMI 2, 27 = USB-C (varies by monitor)",
        "# profile = the Logitech Easy-Switch channel (1-3) that's paired with that computer.",
        "# Leave a key out to not touch that part.",
        "[targets.mac]",
        "input = 17",
        "profile = 2",
        "",
        "[targets.win]",
        "input = 18",
        "profile = 1",
        "",
        "# Logitech devices connected over Bluetooth (not via a USB receiver).",
        "# Add `profiles = { mac = 3 }` to a device if its channels are numbered differently.",
    ]
    for name, pid in devices or [("keyboard", 0xB38F)]:
        lines += ["", "[[logitech]]", f'name = "{name}"', f"pid = 0x{pid:04X}"]
    if not devices:
        lines[-3:-3] = ["# (example - replace with a device from `quickswap discover`)"]
    return "\n".join(lines) + "\n"
