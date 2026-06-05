# Run from REPL or: make test-display
# Draws colour bars across the panel and reports which API is available.
# Use the result to pick which block to uncomment in main.py.

PANEL_W, PANEL_H = 128, 64

BARS = [
    (255,   0,   0),
    (255, 165,   0),
    (255, 255,   0),
    (  0, 255,   0),
    (  0,   0, 255),
    (138,  43, 226),
    (255, 255, 255),
    (  0,   0,   0),
]


def _draw_bars_hub75(display):
    bar_h = PANEL_H // len(BARS)
    for i, (r, g, b) in enumerate(BARS):
        for y in range(i * bar_h, min((i + 1) * bar_h, PANEL_H)):
            for x in range(PANEL_W):
                display.set_rgb(x, y, r, g, b)
    display.flip()


def _draw_bars_picographics(display):
    bar_h = PANEL_H // len(BARS)
    for i, (r, g, b) in enumerate(BARS):
        display.set_pen(display.create_pen(r, g, b))
        for y in range(i * bar_h, min((i + 1) * bar_h, PANEL_H)):
            for x in range(PANEL_W):
                display.pixel(x, y)
    display.update()


def _try_hub75():
    from hub75 import Hub75
    d = Hub75(PANEL_W, PANEL_H)
    d.start()
    _draw_bars_hub75(d)
    return "hub75"


def _try_picographics():
    from interstate75 import Interstate75
    i75 = Interstate75(display=Interstate75.DISPLAY_INTERSTATE75_128X64)
    d = i75.display
    _draw_bars_picographics(d)
    i75.update()
    return "interstate75"


for fn in (_try_hub75, _try_picographics):
    try:
        api = fn()
        print()
        print("=== SUCCESS: API is '{}' ===".format(api))
        print("In main.py: uncomment Option A (hub75)" if api == "hub75"
              else "In main.py: uncomment Option B (picographics)")
        print()
        break
    except (ImportError, AttributeError) as e:
        print("skip {}: {}".format(fn.__name__, e))
else:
    print("ERROR: no working display API found — check firmware version")
