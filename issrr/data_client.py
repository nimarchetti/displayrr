import os
import threading
import time
import logging
from typing import Optional

import requests

log = logging.getLogger("issrr.data")

ISS_URL = os.getenv("ISS_TRACKER_URL", "https://iss.cdnspace.ca").rstrip("/")
OBSERVER_LAT = os.getenv("OBSERVER_LAT", "")
OBSERVER_LON = os.getenv("OBSERVER_LON", "")


class ISSDataClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {
            "orbital": None,
            "solar": None,
            "events": None,
            "passes": None,
            "crew": None,
            "docking": None,
        }

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        try:
            r = requests.get(f"{ISS_URL}{path}", params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            log.debug("GET %s failed: %s", path, exc)
            return None

    def _poll_orbit(self) -> None:
        while True:
            data = self._get("/api/orbit")
            if data:
                with self._lock:
                    self._data["orbital"] = data
            time.sleep(2)

    def _poll_slow(self) -> None:
        while True:
            for key, path in (
                ("solar", "/api/weather"),
                ("events", "/api/events"),
                ("crew", "/api/crew"),
                ("docking", "/api/docking"),
            ):
                data = self._get(path)
                if data is not None:
                    with self._lock:
                        self._data[key] = data

            if OBSERVER_LAT and OBSERVER_LON:
                passes = self._get("/api/passes", {"lat": OBSERVER_LAT, "lon": OBSERVER_LON})
                if passes is not None:
                    with self._lock:
                        self._data["passes"] = passes

            time.sleep(60)

    def start(self) -> None:
        for target in (self._poll_orbit, self._poll_slow):
            threading.Thread(target=target, daemon=True, name=target.__name__).start()
        log.info("Data polling started (tracker=%s)", ISS_URL)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
