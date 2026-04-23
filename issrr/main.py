import os
import time
import json
import logging
import threading

import zmq
from PIL import Image

from data_client import ISSDataClient
from screens import SCREENS

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("issrr")

DISPLAY_WIDTH = int(os.getenv("DISPLAY_WIDTH", "256"))
DISPLAY_HEIGHT = int(os.getenv("DISPLAY_HEIGHT", "64"))
MODE_NAME = os.getenv("MODE_NAME", "issrr")
SWITCHRR_FRAME_ADDRESS = os.getenv("SWITCHRR_FRAME_ADDRESS", "tcp://switchrr:5602")
SWITCHRR_EVENT_ADDRESS = os.getenv("SWITCHRR_EVENT_ADDRESS", "tcp://switchrr:5557")
FRAME_INTERVAL = float(os.getenv("FRAME_INTERVAL_S", "1.0"))
FRAME_SEND_HWM = int(os.getenv("FRAME_SEND_HWM", "5"))


class ISSRRMode:
    def __init__(self) -> None:
        self._screen_idx = 0
        self._lock = threading.Lock()
        self.data = ISSDataClient()

        ctx = zmq.Context()

        self._push = ctx.socket(zmq.PUSH)
        self._push.setsockopt(zmq.SNDHWM, FRAME_SEND_HWM)
        self._push.connect(SWITCHRR_FRAME_ADDRESS)

        self._sub = ctx.socket(zmq.SUB)
        self._sub.connect(SWITCHRR_EVENT_ADDRESS)
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")

    def _handle_event(self, raw: bytes) -> None:
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        ev_type = ev.get("type") or ev.get("event", "")
        direction = ev.get("direction", "")
        if ev_type in ("encoder", "rotary"):
            with self._lock:
                if direction in ("cw", "right"):
                    self._screen_idx = (self._screen_idx + 1) % len(SCREENS)
                elif direction in ("ccw", "left"):
                    self._screen_idx = (self._screen_idx - 1) % len(SCREENS)
            log.debug("Screen %d/%d", self._screen_idx + 1, len(SCREENS))

    def _drain_events(self) -> None:
        while True:
            try:
                raw = self._sub.recv(zmq.NOBLOCK)
                self._handle_event(raw)
            except zmq.Again:
                break

    def _render(self) -> bytes:
        with self._lock:
            idx = self._screen_idx
        img = Image.new("1", (DISPLAY_WIDTH, DISPLAY_HEIGHT), 0)
        try:
            SCREENS[idx].render(img, self.data.snapshot(), idx + 1, len(SCREENS))
        except Exception:
            log.exception("Render error on screen %d", idx + 1)
        return img.tobytes()

    def run(self) -> None:
        log.info("issrr starting (mode=%s, frame=%s)", MODE_NAME, SWITCHRR_FRAME_ADDRESS)
        self.data.start()
        while True:
            self._drain_events()
            frame = self._render()
            try:
                self._push.send(frame, zmq.NOBLOCK)
            except zmq.Again:
                pass
            time.sleep(FRAME_INTERVAL)


if __name__ == "__main__":
    ISSRRMode().run()
