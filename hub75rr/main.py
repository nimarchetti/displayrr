import time
import gc
import micropython
import machine
machine.freq(240_000_000)
from serial_client import SerialClient

try:
    from config import PANEL_W, PANEL_H, WIDTH, HEIGHT
except ImportError:
    raise RuntimeError("config.py missing — copy config.py.sample and edit it")


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
# Main loop — receive frames from Pi Zero over UART, render, flip
# ---------------------------------------------------------------------------
client = SerialClient(baudrate=2_000_000)
print("main: ready, waiting for frames from Pi Zero")

while True:
    try:
        client.fetch_into(_pixels)
        _render(_pixels, _buf, WIDTH, PANEL_W, PANEL_H)
        _flip()
    except Exception as e:
        print("main: error:", e)
        time.sleep(1)
