import time
import micropython
from serial_client import SerialClient

try:
    from config import PANEL_W, PANEL_H, WIDTH, HEIGHT
except ImportError:
    raise RuntimeError("config.py missing — copy config.py.sample and edit it")

# Optional: WiFi + hub75pi URL for button-driven mode switching.
# Set HUB75PI_URL, WIFI_SSID, WIFI_PASSWORD in config.py to enable.
try:
    from config import HUB75PI_URL, WIFI_SSID, WIFI_PASSWORD
    _buttons_enabled = True
except ImportError:
    _buttons_enabled = False

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
from interstate75 import Interstate75

_i75     = Interstate75(display=Interstate75.DISPLAY_INTERSTATE75_256X64)
_display = _i75.display
_buf     = bytearray(PANEL_W * PANEL_H * 4)   # BGRA display framebuffer
_pixels  = bytearray(WIDTH * HEIGHT * 3)       # RGB888 decode buffer
_display.set_framebuffer(_buf)


@micropython.viper
def _render(src: ptr8, dst: ptr32, src_w: int, dst_w: int, h: int):
    for y in range(h):
        row_src = y * src_w
        row_dst = y * dst_w
        for x in range(dst_w):
            i = (row_src + x) * 3
            dst[row_dst + x] = (int(src[i]) << 16) | (int(src[i+1]) << 8) | int(src[i+2])


def _flip():
    _i75.update()


# ---------------------------------------------------------------------------
# Button input → hub75pi HTTP (optional, requires WiFi config in config.py)
# ---------------------------------------------------------------------------
_wlan = None

if _buttons_enabled:
    import network
    import urequests
    from pimoroni import Button

    _btn_a = Button(14)   # A = previous mode
    _btn_b = Button(15)   # B = next mode

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    _wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(20):
        if _wlan.isconnected():
            break
        time.sleep(0.5)
    if _wlan.isconnected():
        print("main: WiFi connected", _wlan.ifconfig()[0])
    else:
        print("main: WiFi failed — buttons disabled")
        _wlan = None


def _post_action(action: str) -> None:
    if _wlan is None or not _wlan.isconnected():
        return
    try:
        r = urequests.post(
            HUB75PI_URL + "/event",
            json={"action": action},
            headers={"Content-Type": "application/json"},
        )
        r.close()
    except Exception as e:
        print("main: button POST failed:", e)


# ---------------------------------------------------------------------------
# Main loop — receive frames from Pi Zero over UART, render, flip
# ---------------------------------------------------------------------------
client = SerialClient(baudrate=2_000_000)
print("main: ready, waiting for frames from Pi Zero")

_last_a = False
_last_b = False

while True:
    try:
        client.fetch_into(_pixels)
        _render(_pixels, _buf, WIDTH, PANEL_W, PANEL_H)
        _flip()
    except Exception as e:
        print("main: error:", e)
        time.sleep(1)

    # Button edge detection — only fires once per press (not held)
    if _buttons_enabled and _wlan is not None:
        a = _btn_a.is_pressed
        b = _btn_b.is_pressed
        if a and not _last_a:
            _post_action("prev")
        if b and not _last_b:
            _post_action("next")
        _last_a = a
        _last_b = b
