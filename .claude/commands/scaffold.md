# /scaffold — New displayrr Mode Container

Scaffold a new displayrr mode container repo from scratch, following the tiderr/issrr pattern and the new multi-display protocol (DISPLAY_REGISTRY + PUB frames).

## Step 1 — Gather requirements

Ask the user the following questions (all in one message):

1. **Mode name** — should follow the `<name>rr` convention (e.g. `weatherrr`, `clockrr`). What is the mode name, and what is the value for `mode_name` in DISPLAY_REGISTRY (usually the same, lowercase, e.g. `"weatherrr"`)?
2. **One-line description** — what does this mode display?
3. **Data source** — where does the data come from? (e.g. a public API with a URL, MQTT, local file, no external data)
4. **Screens** — list the screens (views) the mode should have. Each screen is one full-display layout the user cycles through with the encoder. Give each a short name and one sentence describing what it shows.
5. **Encoder input** — does this mode need to respond to encoder rotation (ENCODER_DELTA) or button presses (ENCODER_PUSH)? If yes, describe the intended behaviour.
6. **Pixel format** — `"L"` (greyscale, default, suits OLED) or `"RGB24"` (colour, for TFT displays)?

## Step 2 — Confirm and create the repo directory

- Confirm the repo path will be `~/code/<mode_name>/`
- Create the directory: `mkdir -p ~/code/<mode_name>`
- All files go inside it

## Step 3 — Generate files

Generate ALL of the following files. Do not skip any.

---

### `main.py`

Follow this structure exactly — it is the authoritative pattern for the new multi-display protocol:

```python
"""
<mode_name> — <one-line description>.

Encoder behaviour:
  ENCODER_DELTA → <describe or 'not used'>
  ENCODER_PUSH  → <describe or 'not used'>
"""
import json
import logging
import os
import threading
import time
from typing import Optional

import zmq
from PIL import Image

from data_client import <ModeName>DataClient
from screens import SCREENS

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("<mode_name>")

MODE_NAME                   = os.getenv("MODE_NAME", "<mode_name>")
SWITCHRR_FRAME_BIND_ADDRESS = os.getenv("SWITCHRR_FRAME_BIND_ADDRESS", "tcp://0.0.0.0:<port>")
SWITCHRR_EVENT_ADDRESS      = os.getenv("SWITCHRR_EVENT_ADDRESS", "tcp://switchrr:5557")
FRAME_INTERVAL              = float(os.getenv("FRAME_INTERVAL_S", "1.0"))
FRAME_SEND_HWM              = int(os.getenv("FRAME_SEND_HWM", "5"))

# Parse DISPLAY_REGISTRY to find display sizes this mode serves.
# Each entry in DISPLAY_REGISTRY whose 'modes' list contains MODE_NAME
# contributes a (width, height) rendering target.
def _parse_display_sizes() -> list[tuple[int, int]]:
    raw = os.getenv("DISPLAY_REGISTRY", "")
    if not raw:
        # Fallback: single display using legacy vars
        w = int(os.getenv("DISPLAY_WIDTH", "256"))
        h = int(os.getenv("DISPLAY_HEIGHT", "64"))
        return [(w, h)]
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("DISPLAY_REGISTRY is not valid JSON; falling back to DISPLAY_WIDTH/HEIGHT")
        w = int(os.getenv("DISPLAY_WIDTH", "256"))
        h = int(os.getenv("DISPLAY_HEIGHT", "64"))
        return [(w, h)]
    sizes = []
    for display in registry:
        for mode in display.get("modes", []):
            if mode.get("mode_name") == MODE_NAME:
                sizes.append((int(display["width"]), int(display["height"])))
                break
    seen: set[tuple[int, int]] = set()
    unique = []
    for s in sizes:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique or [(256, 64)]


DISPLAY_SIZES = _parse_display_sizes()


class <ModeName>Mode:
    def __init__(self) -> None:
        self._screen_idx = 0
        self._sequence   = 0
        self._lock       = threading.Lock()
        self._active     = False

        self.data = <ModeName>DataClient()

        ctx = zmq.Context()

        self._pub = ctx.socket(zmq.PUB)
        self._pub.setsockopt(zmq.SNDHWM, FRAME_SEND_HWM)
        self._pub.bind(SWITCHRR_FRAME_BIND_ADDRESS)

        self._sub = ctx.socket(zmq.SUB)
        self._sub.connect(SWITCHRR_EVENT_ADDRESS)
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")

    def _handle_event(self, raw: bytes) -> None:
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        event = ev.get("event", "")

        if event == "MODE_ACTIVE" and ev.get("mode_name") == MODE_NAME:
            self._active = True
            log.info("active (display_id=%s)", ev.get("display_id", "?"))
            return
        if event == "MODE_INACTIVE" and ev.get("mode_name") == MODE_NAME:
            self._active = False
            log.info("inactive (display_id=%s)", ev.get("display_id", "?"))
            return

        if not self._active:
            return

        with self._lock:
            if event == "ENCODER_DELTA":
                delta = ev.get("delta", 0)
                if delta > 0:
                    self._screen_idx = (self._screen_idx + 1) % len(SCREENS)
                elif delta < 0:
                    self._screen_idx = (self._screen_idx - 1) % len(SCREENS)
                log.debug("Screen %d/%d", self._screen_idx + 1, len(SCREENS))
            elif event == "ENCODER_PUSH":
                pass  # TODO: implement push behaviour if needed

    def _drain_events(self) -> None:
        while True:
            try:
                raw = self._sub.recv(zmq.NOBLOCK)
                self._handle_event(raw)
            except zmq.Again:
                break

    def _render(self, width: int, height: int) -> Image.Image:
        with self._lock:
            idx = self._screen_idx

        snapshot = self.data.snapshot()
        img = Image.new("<pixel_mode>", (width, height), 0)

        screen = SCREENS[idx]
        try:
            screen.render(img, snapshot, width, height)
        except Exception:
            log.exception("Render error screen=%d size=%dx%d", idx + 1, width, height)
        return img

    def _send_frame(self, width: int, height: int, img: Image.Image) -> None:
        try:
            self._pub.send_multipart([
                MODE_NAME.encode(),
                str(width).encode(),
                str(height).encode(),
                img.tobytes(),
            ], zmq.NOBLOCK)
            self._sequence += 1
        except zmq.Again:
            pass

    def run(self) -> None:
        log.info("<mode_name> starting (mode=%s bind=%s sizes=%s)",
                 MODE_NAME, SWITCHRR_FRAME_BIND_ADDRESS, DISPLAY_SIZES)
        self.data.start()
        while True:
            self._drain_events()
            for (w, h) in DISPLAY_SIZES:
                img = self._render(w, h)
                self._send_frame(w, h, img)
            time.sleep(FRAME_INTERVAL)


if __name__ == "__main__":
    <ModeName>Mode().run()
```

Fill in all `<placeholders>`. Use `"L"` for greyscale or `"RGB"` for colour depending on the user's choice.

For the port number in `SWITCHRR_FRAME_BIND_ADDRESS`: suggest `5604` (next available after existing modes). Tell the user to update this if it conflicts.

---

### `data_client.py`

Implement a `<ModeName>DataClient` with:
- `start()` — starts a background daemon thread that fetches/subscribes to the data source and updates internal state
- `snapshot()` — returns a thread-safe copy of the current data as a plain dict
- A `threading.Lock` protecting internal state

If the data source is a REST API, fetch in a loop with a configurable interval. If no data source, `snapshot()` returns `{}` and `start()` is a no-op.

---

### `screens/__init__.py`

```python
from .screen_1 import Screen1
# ... one import per screen

SCREENS = [
    Screen1(),
    # ...
]
```

---

### `screens/base.py`

Copy the shared rendering utilities from the tiderr pattern:
- `get_font(small=False)` — lazy-loads DejaVu Sans Mono 9pt (or 7pt), falls back to PIL default
- `render_header(draw, img_w, title, page, page_count)` — white header bar, black text
- `render_row(draw, row, txt, x, fill, small)` — renders a text row below the header
- `render_pair(draw, row, left, right, img_w)` — two-column row
- `bar(draw, x, y, w, h, fraction)` — horizontal progress bar
- `HEADER_H = 11`, `ROW_H = 10`
- `BaseScreen` class with `title`, `page_count`, `render(img, data, width, height)`, `draw_content(draw, img, data, page, width, height)`

Make `draw_content` accept `width` and `height` — unlike tiderr, screens must be resolution-aware.

---

### `screens/screen_N.py` — one file per screen

For each screen the user described, generate a class that:
- Inherits from `BaseScreen`
- Sets `title = "SCREEN NAME"` and `page_count = 1` (or more if needed)
- Implements `draw_content` to render a plausible skeleton for the described content, using `render_row` / `render_pair` / `bar` from base
- Uses `width` and `height` parameters for layout so it works at any resolution

---

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

---

### `requirements.txt`

Always include:
```
Pillow>=10.0.0
pyzmq>=25.0.0
```

Add `requests>=2.31.0` if the data source is a REST API. Add any other libraries the data_client needs.

---

### `.env.sample`

```
MODE_NAME=<mode_name>
SWITCHRR_FRAME_BIND_ADDRESS=tcp://0.0.0.0:<port>
SWITCHRR_EVENT_ADDRESS=tcp://switchrr:5557
DISPLAY_REGISTRY=  # populated by displayrr .env
DISPLAY_WIDTH=256  # fallback if DISPLAY_REGISTRY not set
DISPLAY_HEIGHT=64
FRAME_INTERVAL_S=1.0
FRAME_SEND_HWM=5
LOG_LEVEL=INFO
# <any mode-specific vars here>
```

---

## Step 4 — Initialise git

Run these commands inside `~/code/<mode_name>/`:

```bash
git init
git add .
git commit -m "feat: initial scaffold for <mode_name>"
```

---

## Step 5 — Print integration instructions

After generating everything, print the following for the user to paste:

**`docker-compose.yml` service block** (to add to `~/code/displayrr/docker-compose.yml`):
```yaml
<mode_name>:
  build: ./<mode_name>
  restart: unless-stopped
  networks:
    - displayrr
  env_file: .env
  environment:
    MODE_NAME: <mode_name>
    SWITCHRR_FRAME_BIND_ADDRESS: "tcp://0.0.0.0:<port>"
    SWITCHRR_EVENT_ADDRESS: "tcp://switchrr:5557"
```

**`DISPLAY_REGISTRY` mode entry** (to add inside the relevant display's `modes` array in `~/code/displayrr/.env`):
```json
{"mode_name":"<mode_name>","display_name":"<display_name>","frame_pub_address":"tcp://<mode_name>:<port>"}
```

**Submodule command** (once the repo is pushed to GitHub):
```bash
git submodule add https://github.com/nimarchetti/<mode_name>.git <mode_name>
```
