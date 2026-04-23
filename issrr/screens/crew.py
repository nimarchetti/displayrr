from .base import BaseScreen, render_row, get_font, text_w, HEADER_H, ROW_H


class CrewScreen(BaseScreen):
    title = "ISS CREW"

    def get_title(self, data: dict) -> str:
        crew = data.get("crew") or {}
        exp = crew.get("expedition", "?")
        return f"CREW  EXP.{exp}"

    def draw_content(self, draw, img, data):
        crew_data = data.get("crew")
        if not crew_data:
            self.no_data(draw, img)
            return

        members = (crew_data.get("crew") or [])[:6]
        f = get_font()

        for i, m in enumerate(members):
            name = m.get("name", "?").upper()
            role = m.get("role", "FE")
            agency = m.get("agency", "?")

            prefix = "CDR  " if role == "CDR" else "     "
            agency_w = text_w(agency) + 4
            avail_w = img.width - text_w(prefix) - agency_w - 4

            while name and text_w(name) > avail_w:
                name = name[:-1]

            y = HEADER_H + 1 + i * ROW_H
            draw.text((2, y), prefix + name, font=f, fill=1)
            draw.text((img.width - agency_w, y), agency, font=f, fill=1)
