from .base import BaseScreen, render_pair, render_row

_RISK = {"low": "LOW", "moderate": "MODERATE", "high": "HIGH", "severe": "SEVERE"}


class WeatherScreen(BaseScreen):
    title = "SPACE WEATHER"

    def draw_content(self, draw, img, data):
        solar = data.get("solar")
        if not solar:
            self.no_data(draw, img)
            return

        kp = solar.get("kpIndex", 0)
        kp_label = solar.get("kpLabel", "")
        xray_class = solar.get("xrayClass", "?")
        xray_flux = solar.get("xrayFlux", 0)
        proton10 = solar.get("protonFlux10MeV", 0)
        proton1 = solar.get("protonFlux1MeV", 0)
        risk = solar.get("radiationRisk", "low")

        render_pair(draw, 0, f"Kp  {kp:.1f}", f"({kp_label})", img.width)
        render_pair(draw, 1, f"XRAY  {xray_class}", f"{xray_flux:.2e} W/m2", img.width)
        render_pair(draw, 2, "PROTON >=1MeV", f"{proton1:.1f} pfu", img.width)
        render_pair(draw, 3, "PROTON >=10MeV", f"{proton10:.1f} pfu", img.width)
        render_row(draw, 4, f"RADIATION RISK  {_RISK.get(risk, risk.upper())}")
