import time as _time
from .base import BaseScreen, get_font, HEADER_H, ROW_H


def _days_docked(ts_ms: int) -> str:
    days = int((_time.time() * 1000 - ts_ms) / (1000 * 86400))
    return f"-{days}d"


def _short_port(port: str) -> str:
    p = port.upper()
    if "FORWARD" in p or "FWD" in p:
        return "FWD"
    if "AFT" in p or "NADIR" in p:
        return "AFT"
    if "ZENITH" in p or "ZEN" in p:
        return "ZEN"
    if "NODE2" in p or "N2" in p or "HARMONY" in p:
        return "N2 "
    if "MRM" in p or "MINI" in p:
        return "MRM"
    if "PMA" in p:
        return "PMA"
    return port[:4].upper()


class DockingScreen(BaseScreen):
    title = "DOCKED VEHICLES"

    def draw_content(self, draw, img, data):
        vehicles = data.get("docking")
        if not vehicles:
            self.no_data(draw, img)
            return

        f = get_font()
        row = 0
        for v in vehicles:
            if row >= 6:
                break
            name = v.get("name", "?").upper()
            port = _short_port(v.get("port", "?"))
            vtype = v.get("type", "?")[:5].upper()
            op = v.get("operator", "?")[:8].upper()
            docked_ts = v.get("dockedAt", 0)
            age = _days_docked(docked_ts) if docked_ts else ""

            y1 = HEADER_H + 1 + row * ROW_H
            draw.text((2, y1), f"{port:<4} {name}", font=f, fill=1)
            row += 1

            if row < 6:
                y2 = HEADER_H + 1 + row * ROW_H
                draw.text((2, y2), f"     {vtype:<6} {op:<8} {age}", font=f, fill=1)
                row += 1
