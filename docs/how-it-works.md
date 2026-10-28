# How it works

## Monitor: DDC/CI

Monitors accept commands over DDC/CI, a small I²C channel inside the HDMI/DisplayPort cable. Input selection is the standard MCCS VCP code `0x60` (Input Source):

| Input | Value |
|---|---|
| DisplayPort 1 | 15 (`0x0F`) |
| DisplayPort 2 | 16 (`0x10`) |
| HDMI 1 | 17 (`0x11`) |
| HDMI 2 | 18 (`0x12`) |
| USB-C | often 27 (`0x1B`), varies by vendor |

Some vendors, LG for example, use non-standard values. If the standard ones don't work, look up your model.

- **macOS:** quickswap runs `m1ddc display <UUID> set input <value>`. It targets the display by UUID because display numbers shift when a MacBook's lid opens or closes.
- **Windows:** quickswap calls the Monitor Configuration API directly: `EnumDisplayMonitors` → `EnumDisplayDevicesW` (to read the PnP id, e.g. `MONITOR\MSI4BA4\...`) → `GetPhysicalMonitorsFromHMONITOR` → `SetVCPFeature(0x60, value)`.

Reading VCP values back is unreliable on many monitors. The MSI G242 returns `110` for every read, while writes work fine. That's why quickswap has no toggle.

## Keyboard and mouse: Logitech HID++ 2.0

The Easy-Switch button sends a HID++ 2.0 command from feature `CHANGE_HOST` (`0x1814`). quickswap sends the same command. For a device connected directly over Bluetooth:

- **Interface:** HID usage page `0xFF43`, usage `0x0202`.
- **Report:** long report `0x11` (20 bytes), device index `0xFF`.

| Step | Request | Reply |
|---|---|---|
| Find the feature index | `ROOT.getFeature(0x1814)` → `11 FF 00 01 18 14 00…` | byte 4 = index (e.g. `0x0A`) |
| Read the hosts | `CHANGE_HOST.getHostInfo` → `11 FF <idx> 01 00…` | byte 4 = number of hosts, byte 5 = current host (0-based) |
| Switch | `CHANGE_HOST.setCurrentHost(n)` → `11 FF <idx> 11 <n> 00…` | none: the device disconnects immediately |
| Read the name (`discover` only) | `DEVICE_NAME` (`0x0005`): `getCount`, then `getDeviceName(offset)` | |

The function byte is `(function << 4) | software_id`. quickswap uses software id `1`.

A device only exists, as far as the OS is concerned, on the computer it's connected to. So a computer can send it to another host but can never pull it back. If the device is already on the target channel, `setCurrentHost` does nothing: the connection stays up.

### Through a USB receiver (not supported yet)

Devices behind a Unifying or Bolt receiver speak the same protocol through the receiver:

- **Receiver ids:** Unifying `0xC52B`/`0xC534`, Bolt `0xC548`.
- **Interface:** usage page `0xFF00`.
- **Addressing:** device index `1`–`6` is the receiver slot. Short `0x10` reports (7 bytes) work for these requests.

| Step | Request | Reply |
|---|---|---|
| Ping a slot | `10 <slot> 00 11 00 00 AA` | A paired, awake device answers with its HID++ version (e.g. `11 <slot> 00 11 04 05 AA` = 4.5). An empty slot answers with an error. |
| Empty slot error | | HID++ 1.0 error `10 <slot> 8F 00 11 09 …` (`0x09` = unknown device) |
| Switch | `10 <slot> <idx> 11 <n> 00 00` | none, same as over Bluetooth |

On the tested LIFT mouse, sending `setCurrentHost` through the Bolt receiver to a channel already paired over Bluetooth moved it to Bluetooth cleanly.

## Gotchas found along the way

- **hidapi on macOS opens devices exclusively by default.** It tries to seize the device, and macOS refuses that for a keyboard or mouse that's in use. The result is an unhelpful `open failed`. Calling `hid_darwin_set_open_exclusive(0)` before opening fixes it, and no Input Monitoring permission is needed. The Python `hidapi` package doesn't wrap this function, so quickswap calls it through `ctypes` on the package's own binary.
- **macOS lists the built-in panel as `(null)`** in `m1ddc display list`, and it has no DDC. quickswap hides it.
- **Windows PowerShell 5.1 reads BOM-less `.ps1` files as ANSI.** An earlier PowerShell-based Windows version broke because of this: UTF-8 characters like `→` turned into `â†’`. quickswap is pure Python now, and its output is ASCII.
- **A new PATH entry doesn't reach terminals that are already open** on Windows. After installing, open a new terminal.
