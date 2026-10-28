"""Picks the monitor backend for this OS. Each backend exposes monitors(), matches() and set_input()."""
import sys


class DdcError(Exception):
    pass


def backend():
    if sys.platform == "darwin":
        from . import ddc_macos
        return ddc_macos
    if sys.platform == "win32":
        from . import ddc_windows
        return ddc_windows
    raise DdcError(f"monitor switching isn't supported on {sys.platform} (macOS and Windows only)")
