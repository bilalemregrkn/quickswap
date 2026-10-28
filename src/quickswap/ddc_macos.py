"""Monitor input switching on macOS (Apple Silicon) through m1ddc."""
import re
import shutil
import subprocess

from .ddc import DdcError

# [2] MSI G242 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)
_LINE = re.compile(r"^\[(\d+)\]\s+(.*?)\s+\(([0-9A-Fa-f-]{36})\)\s*$")


def _m1ddc(*args: str) -> subprocess.CompletedProcess:
    if not shutil.which("m1ddc"):
        raise DdcError("m1ddc not found (install it: brew install m1ddc)")
    return subprocess.run(["m1ddc", *args], capture_output=True, text=True)


def monitors() -> list[tuple[str, str]]:
    """(id, description) per external display. The id is the display UUID."""
    result = []
    for line in _m1ddc("display", "list").stdout.splitlines():
        # The built-in panel shows up nameless as "(null)" and has no DDC.
        if (m := _LINE.match(line.strip())) and m.group(2) != "(null)":
            result.append((m.group(3), m.group(2)))
    return result


def matches(monitor: tuple[str, str], match: str) -> bool:
    uuid, name = monitor
    return match.lower() in name.lower() or match.lower() in uuid.lower()


def set_input(match: str, value: int) -> int:
    """Sends VCP 0x60 to every matching display. Returns how many took the command."""
    ok = 0
    for monitor in monitors():
        if matches(monitor, match):
            # Target by UUID: display numbers shift when the lid opens or closes.
            if _m1ddc("display", monitor[0], "set", "input", str(value)).returncode == 0:
                ok += 1
    return ok
