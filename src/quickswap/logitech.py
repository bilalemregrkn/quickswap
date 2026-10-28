"""Logitech Easy-Switch over Bluetooth via HID++ 2.0 (feature 0x1814 CHANGE_HOST).

Only devices connected directly over Bluetooth are handled, not ones behind a Unifying/Bolt
receiver. A device only listens to the computer it's currently connected to, so a computer
can send it away but can't pull it back.
"""
import ctypes
import sys
import time

import hid

VID = 0x046D
HIDPP_USAGE_PAGE = 0xFF43
DEVICE_INDEX = 0xFF         # Bluetooth-direct (no receiver)
SW_ID = 0x01
LONG_REPORT = 0x11          # 20 bytes

ROOT = 0x0000
DEVICE_NAME = 0x0005
CHANGE_HOST = 0x1814

# hidapi seizes devices on macOS by default, and a keyboard/mouse in use can't be seized
# ("open failed"), so open them shared.
if sys.platform == "darwin":
    ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(0)


class HidppError(Exception):
    pass


def bluetooth_devices() -> list[tuple[int, bytes]]:
    """(pid, path) of every Logitech device with a HID++ interface on this machine."""
    seen, result = set(), []
    for d in hid.enumerate(VID):
        if d["usage_page"] == HIDPP_USAGE_PAGE and d["path"] not in seen:
            seen.add(d["path"])
            result.append((d["product_id"], d["path"]))
    return result


def find(pid: int) -> bytes | None:
    return next((path for p, path in bluetooth_devices() if p == pid), None)


class Device:
    def __init__(self, path: bytes):
        self._h = hid.device()
        self._h.open_path(path)
        self._features: dict[int, int] = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._h.close()

    def request(self, feature_index: int, function: int, *params: int, wait=True):
        msg = [LONG_REPORT, DEVICE_INDEX, feature_index, (function << 4) | SW_ID, *params]
        self._h.write(msg + [0] * (20 - len(msg)))
        if not wait:
            return None
        deadline = time.time() + 2
        while time.time() < deadline:
            r = self._h.read(20, 200)
            if r and r[0] == LONG_REPORT and r[2] == feature_index and r[3] == msg[3]:
                return r
            if r and r[0] == LONG_REPORT and r[2] == 0xFF:
                raise HidppError(f"HID++ error {r[5]:#x}")
        raise HidppError("no response")

    def feature(self, code: int) -> int:
        if code not in self._features:
            index = self.request(ROOT, 0, code >> 8, code & 0xFF)[4]
            if not index:
                raise HidppError(f"device has no feature {code:#06x}")
            self._features[code] = index
        return self._features[code]

    def name(self) -> str:
        index = self.feature(DEVICE_NAME)
        length = self.request(index, 0)[4]
        name = b""
        while len(name) < length:
            name += bytes(self.request(index, 1, len(name))[4:20])
        return name[:length].decode(errors="replace")

    def host_info(self) -> tuple[int, int]:
        """(number of profiles, current profile 1-based)."""
        r = self.request(self.feature(CHANGE_HOST), 0)
        return r[4], r[5] + 1

    def set_host(self, profile: int):
        # The device drops the link immediately, so there's no reply to wait for.
        self.request(self.feature(CHANGE_HOST), 1, profile - 1, wait=False)
