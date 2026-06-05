import time
from interstate75 import Interstate75

i75 = Interstate75(display=Interstate75.DISPLAY_INTERSTATE75_256X64)
g   = i75.display
buf = bytearray(256 * 64 * 4)
g.set_framebuffer(buf)

pen_k = g.create_pen(0, 0, 0)
pen_w = g.create_pen(255, 255, 255)
pen_y = g.create_pen(255, 200, 0)

x, dx = 0, 3
frames, t0 = 0, time.ticks_ms()
while True:
    g.set_pen(pen_k); g.clear()
    g.set_pen(pen_w); g.rectangle(x, 0, 6, 64)
    g.set_pen(pen_y); g.rectangle(128, 0, 6, 64)
    i75.update()
    x += dx
    if x >= 250 or x <= 0: dx = -dx
    frames += 1
    if frames % 300 == 0:
        ms = time.ticks_diff(time.ticks_ms(), t0)
        print("fps:", 300000 // ms, "— watch for stutter on panel")
        t0 = time.ticks_ms()
