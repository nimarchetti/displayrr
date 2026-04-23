from datetime import datetime, timezone
from .base import BaseScreen, get_font, HEADER_H, ROW_H


def _fmt_utc(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%a %d %b %H:%M")


def _countdown(ts_ms: int) -> str:
    diff = int(ts_ms / 1000 - datetime.now(timezone.utc).timestamp())
    sign = "+" if diff < 0 else "-"
    diff = abs(diff)
    d, rem = divmod(diff, 86400)
    h, m = divmod(rem, 3600)
    m //= 60
    if d:
        return f"{sign}{d}d{h:02d}h"
    if h:
        return f"{sign}{h}h{m:02d}m"
    return f"{sign}{m}m"


class EventsScreen(BaseScreen):
    title = "ISS EVENTS"

    def draw_content(self, draw, img, data):
        events_data = data.get("events")
        if not events_data:
            self.no_data(draw, img)
            return

        active = events_data.get("active") or []
        upcoming = events_data.get("upcoming") or []
        f = get_font()
        lines: list[str] = []

        if active:
            ev = active[0]
            etype = ev.get("type", "?").upper()
            title = ev.get("title", "?").upper()
            lines.append(f"[ACTIVE] {etype}")
            lines.append(title[:30])
            if ev.get("actualStart"):
                lines.append(f"Since {_fmt_utc(ev['actualStart'])}")
            lines.append("")

        for ev in upcoming[:2]:
            etype = ev.get("type", "?").upper()
            title = ev.get("title", "?").upper()
            start = ev.get("scheduledStart", 0)
            lines.append(f"{title[:22]} ({etype})")
            if start:
                lines.append(f"{_fmt_utc(start)}  {_countdown(start)}")

        if not lines:
            lines = ["No events scheduled."]

        for i, line in enumerate(lines[:6]):
            y = HEADER_H + 1 + i * ROW_H
            draw.text((2, y), line, font=f, fill=1)
