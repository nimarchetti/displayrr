from interstate75 import Interstate75
import time

i75 = Interstate75(display=Interstate75.DISPLAY_INTERSTATE75_128X64)
g = i75.display

colours = [
    g.create_pen(255, 0, 0),
    g.create_pen(0, 255, 0),
    g.create_pen(0, 0, 255),
    g.create_pen(255, 255, 255),
]

i = 0
while True:
    g.set_pen(colours[i % 4])
    g.clear()
    i75.update()
    print("colour", i % 4)
    i += 1
    time.sleep(1)
