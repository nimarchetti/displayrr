import os
from datetime import datetime, timezone
from .base import BaseScreen, render_row, get_font, HEADER_H, ROW_H

OBSERVER_LAT = os.getenv("OBSERVER_LAT", "")
OBSERVER_LON = os.getenv("OBSERVER_LON", "")

_AZ_NAMES = [
    (22.5, "N"), (67.5, "NE"), (112.5, "E"), (157.5, "SE"),
    (202.5, "S"), (247.5, "SW"), (292.5, "W"), (337.5, "NW"), (360.1, "N"),
]


def _az(deg: float) -> str:
    for threshold, name in _AZ_NAMES:
        if deg < threshold:
            return name
    return "N"


def _fmt_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%a %H:%M")


def _countdown(ts_ms: int) -> str:
    diff = int(ts_ms / 1000 - datetime.now(timezone.utc).timestamp())
    if diff <= 0:
        return "now"
    d, rem = divmod(diff, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"-{d}d{h:02d}h"
    if h:
        return f"-{h}h{m:02d}m"
    return f"-{m}m"


class PassesScreen(BaseScreen):
    title = "VISIBLE PASSES"

    def draw_content(self, draw, img, data):
        if not OBSERVER_LAT or not OBSERVER_LON:
            render_row(draw, 1, "Set OBSERVER_LAT and")
            render_row(draw, 2, "OBSERVER_LON env vars")
            render_row(draw, 3, "for pass predictions.")
            return

        passes = data.get("passes")
        if not passes:
            self.no_data(draw, img)
            return

        f = get_font()
        row = 0
        for p in (passes if isinstance(passes, list) else [])[:2]:
            if row >= 6:
                break
            rise_ms = p.get("riseTime", 0)
            max_el = p.get("maxElevation", 0)
            mag = p.get("magnitude", 0.0)
            quality = p.get("quality", "?").upper()[:6]
            rise_az = _az(p.get("riseAzimuth", 0))
            set_az = _az(p.get("setAzimuth", 0))

            y = HEADER_H + 1 + row * ROW_H
            draw.text((2, y), f"{_fmt_time(rise_ms)} UTC  {_countdown(rise_ms)}", font=f, fill=1)
            row += 1
            if row < 6:
                y = HEADER_H + 1 + row * ROW_H
                draw.text((2, y), f"  MAX {max_el:.0f}deg  Mag {mag:+.1f}  {quality}", font=f, fill=1)
                row += 1
            if row < 6:
                y = HEADER_H + 1 + row * ROW_H
                draw.text((2, y), f"  RISE {rise_az}  ->  SET {set_az}", font=f, fill=1)
                row += 1
            row += 1  # blank row between passes
