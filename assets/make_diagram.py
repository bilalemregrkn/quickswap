"""Renders the animated README diagram (assets/diagram.gif) and an MP4 for social posts.

usage: python assets/make_diagram.py [--mp4 PATH] [--frame SECONDS PNG]
Needs Pillow and ffmpeg. Uses macOS system fonts (SF Pro / SF Mono).
"""
import argparse
import subprocess
import tempfile
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 675          # design units
SS = 2                    # supersampling factor for smooth edges
OUT_W, OUT_H = 1600, 900  # MP4 size; the GIF is scaled down from it
FPS = 20
DURATION = 8.4

BG = (13, 17, 23)
PANEL = (22, 27, 34)
LINE = (48, 54, 61)
TEXT = (230, 237, 243)
MUTED = (125, 133, 144)
MAC = (167, 139, 250)
WIN = (56, 189, 248)
GREEN = (63, 185, 80)

FONTS = Path("/System/Library/Fonts")

# Each switch: monitor, keyboard, mouse move one after another, like the real output.
FORWARD = [1.8, 2.2, 2.6]
BACK = [5.6, 6.0, 6.4]
# Mac = HDMI 1 + profile 1, Windows = HDMI 2 + profile 2, so the numbers line up.
OUT_TO_WIN = ["monitor: win (input 18)", "keyboard: profile 2", "mouse: profile 2"]
OUT_TO_MAC = ["monitor: mac (input 17)", "keyboard: profile 1", "mouse: profile 1"]


@cache
def font(size, mono=False, weight="Regular"):
    f = ImageFont.truetype(str(FONTS / ("SFNSMono.ttf" if mono else "SFNS.ttf")), size * SS)
    f.set_variation_by_name(weight)
    return f


def lerp(a, b, x):
    return tuple(round(p + (q - p) * x) for p, q in zip(a, b)) if isinstance(a, tuple) else a + (b - a) * x


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ramp(t, start, dur=0.4):
    return ease((t - start) / dur)


def bezier(p0, p1, p2, s):
    return tuple((1 - s) ** 2 * a + 2 * (1 - s) * s * b + s * s * c for a, b, c in zip(p0, p1, p2))


class Canvas:
    """ImageDraw in design units."""

    def __init__(self):
        self.img = Image.new("RGB", (W * SS, H * SS), BG)
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def _s(box):
        return [v * SS for v in box]

    def rect(self, box, fill=None, outline=None, width=1, r=0):
        self.d.rounded_rectangle(self._s(box), radius=r * SS, fill=fill, outline=outline, width=width * SS)

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._s(box), fill=fill, outline=outline, width=width * SS)

    def poly(self, points, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in points], fill=fill)

    def curve(self, p0, p1, p2, color, width):
        pts = [bezier(p0, p1, p2, i / 40) for i in range(41)]
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=color, width=round(width * SS), joint="curve")

    def text(self, xy, s, f, fill, anchor="la"):
        self.d.text((xy[0] * SS, xy[1] * SS), s, font=f, fill=fill, anchor=anchor)

    def text_width(self, s, f):
        return self.d.textlength(s, font=f) / SS


def draw_laptop(c, on):
    accent = lerp(LINE, MAC, on)
    c.rect((100, 205, 280, 320), fill=PANEL, outline=accent, width=3, r=8)
    c.rect((110, 215, 270, 310), fill=lerp(BG, (40, 32, 70), on), r=4)
    c.poly([(80, 322), (300, 322), (312, 336), (68, 336)], fill=lerp(LINE, (90, 80, 130), on))
    c.text((190, 172), "Mac", font(22, weight="Semibold"), lerp(MUTED, MAC, on), anchor="mm")


def draw_tower(c, on):
    accent = lerp(LINE, WIN, on)
    c.rect((960, 195, 1060, 336), fill=PANEL, outline=accent, width=3, r=8)
    for y in (215, 228, 241):
        c.rect((978, y, 1042, y + 5), fill=LINE, r=2)
    c.ellipse((1003, 300, 1017, 314), fill=lerp(LINE, WIN, on))
    c.text((1010, 172), "Windows", font(22, weight="Semibold"), lerp(MUTED, WIN, on), anchor="mm")


def draw_monitor(c, m):
    c.rect((450, 150, 750, 330), fill=PANEL, outline=lerp(MAC, WIN, m), width=3, r=10)
    c.rect((590, 330, 610, 356), fill=LINE)
    c.rect((540, 354, 660, 362), fill=LINE, r=4)
    screen = (462, 162, 738, 318)
    # Mac desktop, with the Windows desktop sliding in from the Windows side.
    c.rect(screen, fill=(46, 36, 82), r=4)
    c.rect((462, 162, 738, 172), fill=(70, 58, 112))
    c.rect((560, 300, 640, 310), fill=(90, 76, 140), r=5)
    if m > 0:
        win = Canvas()
        win.rect(screen, fill=(14, 52, 92), r=4)
        win.rect((462, 302, 738, 318), fill=(10, 36, 64))
        win.rect((594, 305, 606, 315), fill=WIN, r=2)
        cut = round((738 - (738 - 462) * m) * SS)
        region = (cut, 162 * SS, 738 * SS, 318 * SS)
        if region[2] > cut:
            c.img.paste(win.img.crop(region), region[:2])


def draw_keyboard(c, k):
    c.rect((420, 420, 700, 482), fill=PANEL, outline=lerp(MAC, WIN, k), width=2, r=10)
    for row in range(3):
        for col in range(12):
            x, y = 432 + col * 22, 430 + row * 16
            c.rect((x, y, x + 17, y + 11), fill=LINE, r=2)


def draw_mouse(c, u):
    c.ellipse((735, 418, 775, 484), fill=PANEL, outline=lerp(MAC, WIN, u), width=2)
    c.rect((753, 428, 757, 444), fill=LINE, r=2)


def draw_cables(c, m):
    # Both HDMI cables are always plugged in; the active one lights up.
    for (p0, p1, p2), color, label, on in [
        (((450, 240), (366, 220), (282, 262)), MAC, "HDMI 1", 1 - m),
        (((750, 240), (854, 220), (958, 262)), WIN, "HDMI 2", m),
    ]:
        c.curve(p0, p1, p2, lerp(LINE, color, on), 2 + 2 * on)
        c.text((p1[0], 210), label, font(15, mono=True), lerp(MUTED, color, on), anchor="mm")


def draw_wireless(c, t, to_mac, to_win, x):
    # Bluetooth: dots flowing from the device to whichever computer it's on. Paths are (start, control, end).
    for (p0, p1, p2), color, alpha in [(to_mac, MAC, 1 - x), (to_win, WIN, x)]:
        if alpha < 0.02:
            continue
        c.curve(p0, p1, p2, lerp(BG, LINE, alpha * 0.6), 1.5)
        for i in range(5):
            s = (t * 0.6 + i / 5) % 1
            px, py = bezier(p0, p1, p2, s)
            r = 3.2
            c.ellipse((px - r, py - r, px + r, py + r), fill=lerp(BG, color, alpha * (0.35 + 0.65 * s)))


def draw_badge(c, xy, text, color):
    f = font(14, mono=True)
    w = c.text_width(text, f) + 18
    c.rect((xy[0] - w / 2, xy[1] - 12, xy[0] + w / 2, xy[1] + 12), fill=PANEL, outline=color, width=1, r=12)
    c.text(xy, text, f, color, anchor="mm")


def draw_terminal(c, t):
    c.rect((60, 520, 1140, 645), fill=PANEL, outline=LINE, width=1, r=12)
    if t < 4.3:
        host, color, prompt, cmd, typed_at, outs, times = "on Mac", MAC, "~ % ", "quickswap win", 0.5, OUT_TO_WIN, FORWARD
    else:
        host, color, prompt, cmd, typed_at, outs, times = "on Windows", WIN, "PS C:\\> ", "quickswap", 4.5, OUT_TO_MAC, BACK
    draw_badge(c, (1080, 545), host, color)

    mono = font(19, mono=True)
    n = max(0, min(len(cmd), int((t - typed_at) / 0.08)))
    typing = 0 < n < len(cmd)
    c.text((84, 548), prompt, mono, MUTED, anchor="lm")
    x = 84 + c.text_width(prompt, mono)
    c.text((x, 548), cmd[:n], mono, TEXT, anchor="lm")
    shown = [o for o, at in zip(outs, times) if t >= at]
    if not shown and (typing or int(t * 2.5) % 2 == 0):
        cx = x + c.text_width(cmd[:n], mono) + 2
        c.rect((cx, 537, cx + 10, 559), fill=TEXT)
    for i, line in enumerate(shown):
        y = 548 + 25 * (i + 1)
        c.text((84, y), "->", mono, GREEN, anchor="lm")
        c.text((84 + c.text_width("-> ", mono), y), line, mono, TEXT, anchor="lm")


def frame(t):
    m, k, u = (ramp(t, a) - ramp(t, b) for a, b in zip(FORWARD, BACK))
    c = Canvas()
    c.text((60, 52), "quickswap", font(34, weight="Bold"), TEXT, anchor="lm")
    c.text((60, 92), "One command moves your monitor, keyboard and mouse to the other computer.",
           font(19), MUTED, anchor="lm")
    c.text((1140, 52), "github.com/bilalemregrkn/quickswap", font(15, mono=True), MUTED, anchor="rm")

    draw_cables(c, m)
    mac_port, win_port = (306, 338), (962, 338)
    draw_wireless(c, t, ((420, 452), (330, 452), mac_port), ((700, 440), (860, 395), win_port), k)
    draw_wireless(c, t, ((755, 418), (560, 380), mac_port), ((775, 451), (900, 451), win_port), u)
    draw_laptop(c, 1 - m)
    draw_tower(c, m)
    draw_monitor(c, m)
    draw_keyboard(c, k)
    draw_mouse(c, u)
    draw_badge(c, (560, 500), "profile 2" if k > 0.5 else "profile 1", lerp(MAC, WIN, k))
    draw_badge(c, (755, 500), "profile 2" if u > 0.5 else "profile 1", lerp(MAC, WIN, u))
    draw_terminal(c, t)
    return c.img.resize((OUT_W, OUT_H), Image.LANCZOS)


def main():
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp4", type=Path, help="also keep the MP4 here")
    ap.add_argument("--frame", nargs=2, metavar=("SECONDS", "PNG"), help="render one frame and exit")
    args = ap.parse_args()

    if args.frame:
        frame(float(args.frame[0])).save(args.frame[1])
        return

    mp4 = args.mp4 or Path(tempfile.mkdtemp()) / "diagram.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                            "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    for i in range(round(DURATION * FPS)):
        enc.stdin.write(frame(i / FPS).tobytes())
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed")

    gif = here / "diagram.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    "fps=20,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:reserve_transparent=0[p];"
                    "[b][p]paletteuse=dither=none", str(gif)], check=True)
    print(f"wrote {gif} ({gif.stat().st_size // 1024} KB)" + (f" and {mp4}" if args.mp4 else ""))


if __name__ == "__main__":
    main()
