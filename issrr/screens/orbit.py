from .base import BaseScreen, render_pair, get_font, text_w, HEADER_H, ROW_H

HALF_CYCLE_S = 46 * 60  # ~46-min half-cycle for ISS day/night


def _hms(sec) -> str:
    if sec is None:
        return "---"
    s = int(abs(sec))
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def _lat(v: float) -> str:
    return f"{abs(v):.2f}{'N' if v >= 0 else 'S'}"


def _lon(v: float) -> str:
    return f"{abs(v):.2f}{'E' if v >= 0 else 'W'}"


class OrbitScreen(BaseScreen):
    title = "ISS ORBIT"

    def draw_content(self, draw, img, data):
        orb = data.get("orbital")
        if not orb:
            self.no_data(draw, img)
            return

        render_pair(draw, 0, f"LAT  {_lat(orb['lat'])}", f"LON  {_lon(orb['lon'])}", img.width)
        render_pair(draw, 1, f"ALT  {orb['altitude']:.1f}km", f"SPD  {orb['speedKmH']:.0f}km/h", img.width)
        render_pair(draw, 2, f"APO  {orb['apoapsis']:.1f}km", f"PER  {orb['periapsis']:.1f}km", img.width)
        render_pair(draw, 3, f"INC  {orb['inclination']:.2f}", f"ECC  {orb['eccentricity']:.6f}", img.width)
        render_pair(draw, 4, f"REV  #{orb['revolutionNumber']}", f"BETA {orb['betaAngle']:+.1f}", img.width)

        # Row 5: phase label | inline progress bar | time to transition
        in_sun = orb.get("isInSunlight", False)
        remaining = orb.get("sunsetIn" if in_sun else "sunriseIn") or 0
        pct = max(0.0, min(1.0, 1.0 - remaining / HALF_CYCLE_S))
        phase_lbl = "SUN" if in_sun else "NIT"
        trans_lbl = (
            f"NIGHT {_hms(orb.get('sunsetIn'))}" if in_sun
            else f"SUN   {_hms(orb.get('sunriseIn'))}"
        )

        f = get_font()
        y = HEADER_H + 1 + 5 * ROW_H
        draw.text((2, y), phase_lbl, font=f, fill=1)
        pw = text_w(phase_lbl)
        tw = text_w(trans_lbl)
        bx0 = 2 + pw + 3
        bx1 = img.width - tw - 5
        by = y + 2
        if bx1 > bx0 + 6:
            draw.rectangle([bx0, by, bx1, by + 4], outline=1, fill=0)
            filled = int(pct * (bx1 - bx0 - 2))
            if filled > 0:
                draw.rectangle([bx0 + 1, by + 1, bx0 + 1 + filled - 1, by + 3], fill=1)
        draw.text((img.width - tw - 2, y), trans_lbl, font=f, fill=1)
