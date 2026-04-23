"""Self-contained ISS data client.

Polls public APIs directly (no dependency on cdnspace-iss-tracker):
  TLE         — CelesTrak / ivanstanojevic fallback
  Orbital     — skyfield SGP4 propagation
  Space wx    — NOAA SWPC
  Crew        — Corquaid GitHub Pages
  Docking     — Corquaid GitHub Pages
  Events      — Space Devs Launch Library 2
  Passes      — skyfield find_events
"""
import math
import os
import threading
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from skyfield.api import load, EarthSatellite, wgs84

log = logging.getLogger("issrr.data")

_Re = 6378.137
_GM = 398600.4418
_TAU = 2 * math.pi

_TLE_SOURCES = [
    "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE",
    "https://tle.ivanstanojevic.me/api/tle/25544",
]
_NOAA_KP_URL     = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
_NOAA_XRAY_URL   = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"
_NOAA_PROTON_URL = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json"
_CREW_URL   = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
_DOCK_URL   = "https://corquaid.github.io/international-space-station-APIs/JSON/iss-docked-spacecraft.json"
_EVENTS_URL = "https://ll.thespacedevs.com/2.2.0/event/upcoming/?format=json&limit=10&search=ISS"

OBSERVER_LAT = os.getenv("OBSERVER_LAT", "")
OBSERVER_LON = os.getenv("OBSERVER_LON", "")

_ts = load.timescale(builtin=True)

_TLE_REFRESH_S = 3600
_SLOW_POLL_S   = 60
_ORBIT_POLL_S  = 2


# ---------------------------------------------------------------------------
# Solar geometry
# ---------------------------------------------------------------------------

def _sun_eci_unit(jd_tt: float):
    """Jean Meeus Ch.25 approximate Sun ECI unit vector."""
    T = (jd_tt - 2451545.0) / 36525.0
    L0 = math.radians(280.46646 + 36000.76983 * T + 0.0003032 * T * T)
    M  = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C  = math.radians(
        (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
        + (0.019993 - 0.000101 * T) * math.sin(2 * M)
        + 0.000289 * math.sin(3 * M)
    )
    lon = L0 + C
    eps = math.radians(23.439291111 - 0.013004167 * T - 0.000000164 * T * T)
    x = math.cos(lon)
    y = math.cos(eps) * math.sin(lon)
    z = math.sin(eps) * math.sin(lon)
    mag = math.sqrt(x * x + y * y + z * z)
    return x / mag, y / mag, z / mag


def _is_sunlit(pos_km, sun_hat) -> bool:
    """Cylindrical shadow model."""
    dot = -(pos_km[0]*sun_hat[0] + pos_km[1]*sun_hat[1] + pos_km[2]*sun_hat[2])
    if dot < 0:
        return True
    r_sq = pos_km[0]**2 + pos_km[1]**2 + pos_km[2]**2
    return r_sq - dot * dot > _Re * _Re


def _terminator_crossing(sat, t0_tt: float, in_sun: bool) -> Optional[float]:
    """Seconds until next day/night transition (30-second stepping)."""
    step_s = 30
    for step in range(1, int(47 * 60 / step_s) + 1):
        jd = t0_tt + step * step_s / 86400.0
        pos = list(sat.at(_ts.tt_jd(jd)).position.km)
        if _is_sunlit(pos, _sun_eci_unit(jd)) != in_sun:
            return float(step * step_s)
    return None


# ---------------------------------------------------------------------------
# TLE
# ---------------------------------------------------------------------------

def _fetch_tle() -> Optional[tuple]:
    for url in _TLE_SOURCES:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            if "ivanstanojevic" in url:
                j = r.json()
                return j.get("name", "ISS (ZARYA)"), j["line1"], j["line2"]
            lines = [ln.strip() for ln in r.text.strip().splitlines() if ln.strip()]
            if len(lines) >= 3:
                return lines[0], lines[1], lines[2]
            if len(lines) == 2:
                return "ISS (ZARYA)", lines[0], lines[1]
        except Exception as exc:
            log.debug("TLE fetch from %s failed: %s", url, exc)
    return None


# ---------------------------------------------------------------------------
# Orbital computation
# ---------------------------------------------------------------------------

def _compute_orbital(sat: EarthSatellite) -> Optional[dict]:
    try:
        t   = _ts.now()
        geo = sat.at(t)
        pos = list(geo.position.km)
        vel = list(geo.velocity.km_per_s)
        sub = wgs84.subpoint(geo)

        satrec    = sat.model
        n_rad_s   = satrec.no_kozai / 60.0
        a_km      = (_GM / n_rad_s ** 2) ** (1.0 / 3.0)
        ecc       = satrec.ecco
        rev_num   = int(satrec.revnum + satrec.no_kozai * 1440 / _TAU * (t.tt - sat.epoch.tt))

        hx = pos[1]*vel[2] - pos[2]*vel[1]
        hy = pos[2]*vel[0] - pos[0]*vel[2]
        hz = pos[0]*vel[1] - pos[1]*vel[0]
        hmag = math.sqrt(hx*hx + hy*hy + hz*hz)
        h_hat = (hx/hmag, hy/hmag, hz/hmag)

        sun_hat = _sun_eci_unit(t.tt)
        beta    = math.degrees(math.asin(max(-1.0, min(1.0,
                      sum(h_hat[i]*sun_hat[i] for i in range(3))))))
        in_sun  = _is_sunlit(pos, sun_hat)
        crossing = _terminator_crossing(sat, t.tt, in_sun)

        result: dict = {
            "lat":              sub.latitude.degrees,
            "lon":              sub.longitude.degrees,
            "altitude":         sub.elevation.km,
            "speedKmH":         math.sqrt(sum(v*v for v in vel)) * 3600,
            "apoapsis":         a_km * (1 + ecc) - _Re,
            "periapsis":        a_km * (1 - ecc) - _Re,
            "inclination":      math.degrees(satrec.inclo),
            "eccentricity":     ecc,
            "revolutionNumber": rev_num,
            "betaAngle":        beta,
            "isInSunlight":     in_sun,
        }
        result["sunsetIn" if in_sun else "sunriseIn"] = crossing
        return result
    except Exception as exc:
        log.warning("Orbital computation error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Space weather
# ---------------------------------------------------------------------------

def _classify_kp(kp: float) -> str:
    if kp < 3: return "Quiet"
    if kp < 4: return "Unsettld"
    if kp < 5: return "Active"
    if kp < 6: return "G1 Storm"
    if kp < 7: return "G2 Storm"
    if kp < 8: return "G3 Storm"
    if kp < 9: return "G4 Storm"
    return "G5 Storm"


def _classify_xray(flux: float) -> str:
    if flux < 1e-7: return f"A{flux/1e-8:.1f}"
    if flux < 1e-6: return f"B{flux/1e-7:.1f}"
    if flux < 1e-5: return f"C{flux/1e-6:.1f}"
    if flux < 1e-4: return f"M{flux/1e-5:.1f}"
    return f"X{flux/1e-4:.1f}"


def _radiation_risk(kp: float, xray: float, proton10: float) -> str:
    if xray >= 1e-3 or proton10 > 100 or kp >= 8: return "severe"
    if xray >= 1e-4 or proton10 > 10  or kp >= 7: return "high"
    if xray >= 1e-5 or proton10 > 1   or kp >= 5: return "moderate"
    return "low"


def _fetch_solar() -> Optional[dict]:
    kp_val = 0.0
    try:
        for row in reversed(requests.get(_NOAA_KP_URL, timeout=10).json()):
            try:
                v = float(row[1])
                if v >= 0:
                    kp_val = v
                    break
            except (ValueError, IndexError, TypeError):
                pass
    except Exception as exc:
        log.debug("Kp fetch: %s", exc)

    xray_flux = 1e-9
    try:
        for e in reversed(requests.get(_NOAA_XRAY_URL, timeout=10).json()):
            if e.get("energy") == "0.1-0.8nm":
                try:
                    f = float(e["flux"])
                    if f > 0:
                        xray_flux = f
                        break
                except (ValueError, KeyError):
                    pass
    except Exception as exc:
        log.debug("X-ray fetch: %s", exc)

    proton1 = proton10 = 0.0
    try:
        p1_done = p10_done = False
        for e in reversed(requests.get(_NOAA_PROTON_URL, timeout=10).json()):
            energy = e.get("energy", "")
            try:
                f = max(0.0, float(e.get("flux") or 0))
            except (ValueError, TypeError):
                f = 0.0
            if not p1_done and energy.startswith(">=1 "):
                proton1 = f; p1_done = True
            if not p10_done and energy.startswith(">=10 "):
                proton10 = f; p10_done = True
            if p1_done and p10_done:
                break
    except Exception as exc:
        log.debug("Proton fetch: %s", exc)

    return {
        "kpIndex":        kp_val,
        "kpLabel":        _classify_kp(kp_val),
        "xrayClass":      _classify_xray(xray_flux),
        "xrayFlux":       xray_flux,
        "protonFlux1MeV":  proton1,
        "protonFlux10MeV": proton10,
        "radiationRisk":  _radiation_risk(kp_val, xray_flux, proton10),
    }


# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

_AGENCY_NORM = {
    "Roscosmos": "RSA", "NASA": "NASA", "ESA": "ESA",
    "JAXA": "JAXA", "CSA": "CSA", "UAE": "UAE", "CMSA": "CMSA",
}


def _norm_agency(raw: str) -> str:
    return _AGENCY_NORM.get(raw, (raw or "?")[:5])


def _norm_role(raw: str) -> str:
    r = (raw or "").lower()
    if "commander" in r: return "CDR"
    if "pilot" in r:     return "PLT"
    return "FE"


def _fetch_crew() -> Optional[dict]:
    try:
        data   = requests.get(_CREW_URL, timeout=10).json()
        people = data.get("people", [])
        crew   = [
            {
                "name":   p.get("name", "?"),
                "role":   _norm_role(p.get("title") or p.get("role", "")),
                "agency": _norm_agency(p.get("agency", "")),
            }
            for p in people if p.get("iss") is not False
        ]
        return {"expedition": data.get("expedition", "?"), "crew": crew}
    except Exception as exc:
        log.debug("Crew fetch: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Docking
# ---------------------------------------------------------------------------

def _parse_dt_ms(s: str) -> int:
    if not s:
        return 0
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def _fetch_docking() -> Optional[list]:
    try:
        raw = requests.get(_DOCK_URL, timeout=10).json()
        lst = raw if isinstance(raw, list) else raw.get("spacecraft", raw.get("docked", []))
        return [
            {
                "name":     (s.get("name") or "?"),
                "port":     (s.get("port") or "?"),
                "type":     (s.get("type") or s.get("spacecraft_type") or "?")[:10],
                "operator": (s.get("operator") or s.get("agency") or "?")[:8],
                "dockedAt": _parse_dt_ms(s.get("docked") or s.get("docking_date") or ""),
            }
            for s in lst
        ]
    except Exception as exc:
        log.debug("Docking fetch: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Events (Space Devs)
# ---------------------------------------------------------------------------

_EV_TYPE_MAP = {
    1: "launch", 2: "docking", 3: "eva",
    4: "berthing", 5: "landing", 6: "maneuver", 8: "undocking",
}


def _fetch_events() -> Optional[dict]:
    try:
        results = requests.get(_EVENTS_URL, timeout=15).json().get("results", [])
        now_ms  = int(time.time() * 1000)
        active, upcoming = [], []
        for ev in results:
            name     = ev.get("name", "?")
            ev_type  = ev.get("type") or {}
            type_str = (_EV_TYPE_MAP.get(ev_type.get("id"), ev_type.get("name", "event"))
                        if isinstance(ev_type, dict) else str(ev_type))
            ev_ms    = _parse_dt_ms(ev.get("date", ""))
            status   = ev.get("status") or {}
            is_live  = "live" in (status.get("name", "") if isinstance(status, dict) else "").lower()
            if is_live or (0 < ev_ms < now_ms and now_ms - ev_ms < 86_400_000):
                active.append({"type": type_str, "title": name, "actualStart": ev_ms})
            elif ev_ms > now_ms:
                upcoming.append({"type": type_str, "title": name, "scheduledStart": ev_ms})
        return {"active": active[:3], "upcoming": upcoming[:5]}
    except Exception as exc:
        log.debug("Events fetch: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pass prediction
# ---------------------------------------------------------------------------

def _compute_passes(sat: EarthSatellite) -> Optional[list]:
    if not OBSERVER_LAT or not OBSERVER_LON:
        return None
    try:
        obs_lat, obs_lon = float(OBSERVER_LAT), float(OBSERVER_LON)
    except ValueError:
        return None
    try:
        observer = wgs84.latlon(obs_lat, obs_lon)
        t0 = _ts.now()
        t1 = _ts.tt_jd(t0.tt + 2.0)
        times, events = sat.find_events(observer, t0, t1, altitude_degrees=10.0)

        passes, i = [], 0
        while i < len(events) and len(passes) < 4:
            if events[i] != 0:
                i += 1
                continue
            rise_t = times[i]
            max_t = set_t = None
            j = i + 1
            while j < len(events):
                if events[j] == 1:
                    max_t = times[j]
                elif events[j] == 2:
                    set_t = times[j]
                    break
                j += 1
            if max_t and set_t:
                diff = sat - observer
                _, rise_az, _   = diff.at(rise_t).altaz()
                max_el, _, dist = diff.at(max_t).altaz()
                _, set_az, _    = diff.at(set_t).altaz()
                el = max_el.degrees
                passes.append({
                    "riseTime":     int(rise_t.utc_datetime().timestamp() * 1000),
                    "maxElevation": el,
                    "magnitude":    round(-1.3 + 5.0 * math.log10(max(1.0, dist.km) / 1000.0), 1),
                    "quality":      ("Excellent" if el >= 60 else "Good" if el >= 40
                                     else "Fair" if el >= 20 else "Poor"),
                    "riseAzimuth":  rise_az.degrees,
                    "setAzimuth":   set_az.degrees,
                })
            i = j + 1 if set_t else i + 1
        return passes
    except Exception as exc:
        log.warning("Pass computation error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class ISSDataClient:
    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._sat: Optional[EarthSatellite] = None
        self._tle_at: float = 0
        self._data: dict = {
            "orbital": None, "solar": None, "events": None,
            "passes":  None, "crew":  None, "docking": None,
        }

    def _refresh_tle(self) -> None:
        if self._sat and time.time() - self._tle_at < _TLE_REFRESH_S:
            return
        result = _fetch_tle()
        if result:
            name, l1, l2 = result
            self._sat   = EarthSatellite(l1, l2, name, _ts)
            self._tle_at = time.time()
            log.info("TLE loaded (epoch %s)", self._sat.epoch.utc_iso())

    def _poll_orbit(self) -> None:
        while True:
            try:
                self._refresh_tle()
                if self._sat:
                    orb = _compute_orbital(self._sat)
                    if orb:
                        with self._lock:
                            self._data["orbital"] = orb
            except Exception as exc:
                log.warning("Orbit poll: %s", exc)
            time.sleep(_ORBIT_POLL_S)

    def _poll_slow(self) -> None:
        while True:
            try:
                for key, fn in (("solar", _fetch_solar), ("crew", _fetch_crew),
                                ("docking", _fetch_docking), ("events", _fetch_events)):
                    val = fn()
                    if val is not None:
                        with self._lock:
                            self._data[key] = val
                if self._sat:
                    passes = _compute_passes(self._sat)
                    if passes is not None:
                        with self._lock:
                            self._data["passes"] = passes
            except Exception as exc:
                log.warning("Slow poll: %s", exc)
            time.sleep(_SLOW_POLL_S)

    def start(self) -> None:
        for target in (self._poll_orbit, self._poll_slow):
            threading.Thread(target=target, daemon=True, name=target.__name__).start()
        log.info("ISS data polling started (self-contained, observer=%s/%s)",
                 OBSERVER_LAT or "unset", OBSERVER_LON or "unset")

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
