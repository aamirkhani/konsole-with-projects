"""ColorPicker engine - screen color capture and format conversion."""

import subprocess
import re
from typing import Optional, Tuple


class ColorPickerEngine:
    """Convert colors between formats and capture from screen."""

    FORMATS = ["HEX", "RGB", "HSL", "HSV", "CMYK", "Decimal", "HSB", "XYZ", "LAB"]

    @staticmethod
    def rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
        rf, gf, bf = r / 255, g / 255, b / 255
        cmax, cmin = max(rf, gf, bf), min(rf, gf, bf)
        delta = cmax - cmin
        l = (cmax + cmin) / 2
        if delta == 0:
            h = s = 0.0
        else:
            s = delta / (1 - abs(2 * l - 1))
            if cmax == rf:
                h = 60 * (((gf - bf) / delta) % 6)
            elif cmax == gf:
                h = 60 * (((bf - rf) / delta) + 2)
            else:
                h = 60 * (((rf - gf) / delta) + 4)
        return round(h, 1), round(s * 100, 1), round(l * 100, 1)

    @staticmethod
    def rgb_to_hsv(r: int, g: int, b: int) -> Tuple[float, float, float]:
        rf, gf, bf = r / 255, g / 255, b / 255
        cmax, cmin = max(rf, gf, bf), min(rf, gf, bf)
        delta = cmax - cmin
        v = cmax
        s = 0.0 if cmax == 0 else delta / cmax
        if delta == 0:
            h = 0.0
        elif cmax == rf:
            h = 60 * (((gf - bf) / delta) % 6)
        elif cmax == gf:
            h = 60 * (((bf - rf) / delta) + 2)
        else:
            h = 60 * (((rf - gf) / delta) + 4)
        return round(h, 1), round(s * 100, 1), round(v * 100, 1)

    @staticmethod
    def rgb_to_cmyk(r: int, g: int, b: int) -> Tuple[float, float, float, float]:
        if r == g == b == 0:
            return 0.0, 0.0, 0.0, 100.0
        rf, gf, bf = r / 255, g / 255, b / 255
        k = 1 - max(rf, gf, bf)
        c = (1 - rf - k) / (1 - k)
        m = (1 - gf - k) / (1 - k)
        y = (1 - bf - k) / (1 - k)
        return round(c * 100, 1), round(m * 100, 1), round(y * 100, 1), round(k * 100, 1)

    @staticmethod
    def rgb_to_xyz(r: int, g: int, b: int) -> Tuple[float, float, float]:
        def linearize(c):
            c /= 255
            return (c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        rl, gl, bl = linearize(r), linearize(g), linearize(b)
        x = rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375
        y = rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750
        z = rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041
        return round(x * 100, 4), round(y * 100, 4), round(z * 100, 4)

    def format_color(self, r: int, g: int, b: int, fmt: str) -> str:
        if fmt == "HEX":
            return self.rgb_to_hex(r, g, b)
        elif fmt == "RGB":
            return f"rgb({r}, {g}, {b})"
        elif fmt == "HSL":
            h, s, l = self.rgb_to_hsl(r, g, b)
            return f"hsl({h}°, {s}%, {l}%)"
        elif fmt == "HSV" or fmt == "HSB":
            h, s, v = self.rgb_to_hsv(r, g, b)
            return f"hsv({h}°, {s}%, {v}%)"
        elif fmt == "CMYK":
            c, m, y, k = self.rgb_to_cmyk(r, g, b)
            return f"cmyk({c}%, {m}%, {y}%, {k}%)"
        elif fmt == "Decimal":
            return str(r * 65536 + g * 256 + b)
        elif fmt == "XYZ":
            x, y, z = self.rgb_to_xyz(r, g, b)
            return f"XYZ({x}, {y}, {z})"
        return self.rgb_to_hex(r, g, b)

    def pick_from_screen(self) -> Optional[Tuple[int, int, int]]:
        """Use xcolor, gpick, or xdotool to capture a pixel color."""
        # Try xcolor
        try:
            result = subprocess.run(["xcolor", "--format", "rgb"], capture_output=True, text=True, timeout=60)
            m = re.match(r"rgb:(\w+)/(\w+)/(\w+)", result.stdout.strip())
            if m:
                r = int(m.group(1)[:2], 16)
                g = int(m.group(2)[:2], 16)
                b = int(m.group(3)[:2], 16)
                return r, g, b
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try GNOME screenshot portal
        try:
            result = subprocess.run(
                ["gdbus", "call", "--session", "--dest", "org.gnome.Shell",
                 "--object-path", "/org/gnome/Shell", "--method",
                 "org.gnome.Shell.Eval", "global.get_pointer()"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None
