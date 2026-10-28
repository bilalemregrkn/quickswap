# AGENTS.md

Instructions for AI coding agents helping a user with quickswap. Humans: see [README.md](README.md).

quickswap switches a shared monitor's input (DDC/CI) and the Easy-Switch channel of Logitech Bluetooth keyboards/mice (HID++) between computers. You'll usually be asked to do one of two things:

- **Set it up** on the user's machine. Their hardware is supported → follow [Setup](#setup).
- **Make it work** on hardware the code doesn't handle → follow [Discovery](#discovery-when-the-code-doesnt-cover-the-hardware), then extend the code.

Protocol details and byte layouts: [docs/how-it-works.md](docs/how-it-works.md). Read it before sending raw DDC or HID++ commands.

## Ground rules

**You can't see the desk.** Monitor and device changes are physical. After every action that should be visible, ask the user what happened, e.g. "Did the screen get darker?" or "Did the keyboard stop typing here?". Don't infer success from exit codes: m1ddc and `SetVCPFeature` report success even when the monitor ignores the command.

**Know which commands disconnect the user.** Only run a disruptive command after telling the user what will go away and how to get it back, and after they say go.

| Safe (read-only) | Disruptive |
|---|---|
| `quickswap discover`, `status`, `config`, `--help` | `quickswap <target>` |
| `m1ddc display list`, `m1ddc get …` | Any VCP `0x60` (input) write |
| HID++ `getFeature`, `getHostInfo`, device name | HID++ `setCurrentHost` |
| VCP `0x10` (brightness) write: visible but harmless | |

Recovery paths to give the user before a disruptive step:

- **Monitor:** the monitor's own input button. Or, on a Mac with the lid open, run `quickswap <this machine>` from the built-in keyboard.
- **Keyboard/mouse:** press the device's Easy-Switch button for this computer's channel. **No software on this computer can bring a device back once it's gone**: it now only exists on the other computer.
- **MacBook in clamshell mode:** if the external monitor goes away, the Mac has no display and may sleep. Recover from the other computer or with the monitor button.

**Make monitor tests revert themselves.** Run the switch and the switch back in one background command, e.g. `m1ddc set input 18; sleep 10; m1ddc set input 17`. That way a failed test doesn't strand the user on the other input.

**Test in this order:** read-only → brightness write → input switch with auto-revert → device switch (with the user's go-ahead) → full `quickswap <target>`.

**Keep personal identifiers out of anything public.** That includes issues, PRs, and commits to this repo. Don't post display UUIDs, Bluetooth addresses, host or pairing names, or usernames in paths. Product ids (`0xB38F`) and monitor models are fine.

## Setup

Per computer. Each computer gets its own config.

1. **Prerequisites**
   - macOS: Apple Silicon (check with `uname -m` → `arm64`). Then `brew install m1ddc pipx`.
   - Windows: Python 3.11+ and pipx.
     - The `python` on PATH may be the Microsoft Store stub. Check with `py -3 --version`.
     - After `pipx ensurepath`, already-open terminals keep the old PATH. Tell the user to open a new one.
2. **Install:** `pipx install git+<repo url>`, or `pipx install .` from a clone.
3. **Pair the devices**, if not done already. Each computer gets its own channel. Recommend the same channel numbers on every device: if they differ, per-device `profiles` overrides are needed. To pair, the user selects the channel, holds its button about 3 s until the light blinks fast, then adds the device in Bluetooth settings. If a device is on a USB receiver, see [Logitech device not listed](#logitech-device-not-listed).
4. **Discover:** `quickswap discover`. You should see the monitor and every Logitech device with "(N profiles, now on X)". "Now on X" tells you which channel this computer is paired on.
5. **Config:** `quickswap init`, then edit the file (path from `quickswap config`). Ask the user:
   - which monitor port each computer uses (`input`),
   - which channel each computer is on (`profile`),
   - what to call the targets (the template uses `mac`/`win`).
   - `default` should be the *other* computer.
6. **Status:** `quickswap status`. The monitor should be `[x]` and the devices "connected here".
7. **Monitor test:** brightness first (macOS: `m1ddc set luminance 30`, then back), then an auto-reverting input switch. Ask the user after each.
8. **Full test:** warn the user, then `quickswap <other>`. Tell them to run `quickswap <this one>` on the other computer to come back. Coming back is the other computer's job.

## Discovery (when the code doesn't cover the hardware)

### Monitor doesn't respond

- **Reads are garbage.** Many monitors return nonsense for every read (the MSI G242 returns `110`). That's normal. Judge by writes the user can see, not by reads.
- **Brightness write does nothing.** DDC/CI is probably disabled in the monitor's on-screen menu, so ask the user to turn it on. On macOS, some built-in HDMI ports don't pass DDC. A USB-C → HDMI/DP adapter or cable usually does.
- **Brightness works, input doesn't.** The monitor may use non-standard input values; some vendors, LG for example, do. Search for the model's values. Then try candidates with auto-revert while the user watches.
- **Intel Mac or Linux.** m1ddc is Apple Silicon only. Possible backends are `ddcctl` / BetterDisplay's CLI (Intel Mac) and `ddcutil` (Linux). A new backend means a `ddc_<os>.py` module with `monitors()`, `matches()` and `set_input()`, registered in `ddc.py`.

### Logitech device not listed

`discover` lists only devices with a Bluetooth HID++ interface (vendor `0x046D`, usage page `0xFF43`).

- **Device is on a Unifying/Bolt receiver.** The receiver shows up as `0xC52B`/`0xC534` (Unifying) or `0xC548` (Bolt), usage page `0xFF00`. Devices sit at device index `1`–`6`.
  - **Find the slot.** Send a short `0x10` ping to each index and look for a reply. A HID++ 1.0 error `0x8F` with code `0x09` means the slot is empty.
  - **Same commands, different framing.** `CHANGE_HOST` works through the receiver too: device index = slot, short reports.
  - **Moving it to Bluetooth.** Use `setCurrentHost` through the receiver to send the device to a channel that's already paired over Bluetooth. Or have the user pair a channel over Bluetooth, which replaces the receiver pairing on that channel. Supporting receivers in the code is a welcome contribution.
- **`open failed` on macOS.** That's hidapi trying to open the device exclusively. `logitech.py` already calls `hid_darwin_set_open_exclusive(0)`; any ad-hoc script needs to call it too.
- **Device has no `CHANGE_HOST` (`0x1814`)** → it can't be switched from software.

### Reading what's stored on each channel

On some devices, feature `0x1815` (HOSTS_INFO) gives each channel's bus type and stored host name. It's useful to see which computer a channel is paired with. Byte layouts vary, so treat names as hints.

## Changing the code

| File | What it does |
|---|---|
| `src/quickswap/cli.py` | Commands and output |
| `src/quickswap/config.py` | TOML config: loading, validation, `init` template |
| `src/quickswap/logitech.py` | HID++ over Bluetooth |
| `src/quickswap/ddc.py` | Picks the monitor backend |
| `src/quickswap/ddc_macos.py` | m1ddc backend |
| `src/quickswap/ddc_windows.py` | dxva2 backend (ctypes) |

- Keep the output ASCII (`->`, not `→`). Windows consoles and pipes mangle UTF-8.
- Keep `status` and `discover` read-only.
- There's no test suite that touches hardware. Verify on real devices with the user, following the order in [Ground rules](#ground-rules).
- Record what you verify, and on which hardware, in README's "Tested with" table. Don't mark untested paths as working.
