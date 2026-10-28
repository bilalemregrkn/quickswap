"""Monitor input switching on Windows through the built-in Monitor Configuration API (dxva2)."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)


class PHYSICAL_MONITOR(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]


def _outputs() -> list[tuple[int, str, list[tuple[str, str]]]]:
    """(HMONITOR, adapter output like \\\\.\\DISPLAY1, [(PnP id, name), ...]) per active display."""
    handles = []
    callback = MONITORENUMPROC(lambda h, dc, rect, data: handles.append(h) or True)
    user32.EnumDisplayMonitors(None, None, callback, 0)
    result = []
    for h in handles:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(h, ctypes.byref(info)):
            continue
        attached, i = [], 0
        while True:
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(dd)
            if not user32.EnumDisplayDevicesW(info.szDevice, i, ctypes.byref(dd), 0):
                break
            attached.append((dd.DeviceID, dd.DeviceString))
            i += 1
        result.append((h, info.szDevice, attached))
    return result


def monitors() -> list[tuple[str, str]]:
    """(id, description) per monitor. The id is the PnP id, e.g. MONITOR\\MSI4BA4\\{...}\\0004."""
    return [(pnp, f"{adapter}  {name}") for _, adapter, attached in _outputs() for pnp, name in attached]


def matches(monitor: tuple[str, str], match: str) -> bool:
    return match.lower() in monitor[0].lower()


def set_input(match: str, value: int) -> int:
    """Sends VCP 0x60 to every matching monitor. Returns how many took the command."""
    ok = 0
    for h, _, attached in _outputs():
        if not any(matches((pnp, name), match) for pnp, name in attached):
            continue
        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(h, ctypes.byref(count)) or not count.value:
            continue
        physical = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(h, count, physical):
            continue
        try:
            for pm in physical:
                if dxva2.SetVCPFeature(pm.hPhysicalMonitor, 0x60, value):
                    ok += 1
        finally:
            dxva2.DestroyPhysicalMonitors(count, physical)
    return ok
