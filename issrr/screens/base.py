import os
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

_font_instance: Optional[ImageFont.ImageFont] = None

_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
)
_FONT_SIZE = 8

# Layout constants for a 256x64 display.
# Header row: 10px tall (fits 8px glyphs with 1px top padding).
# Content rows: 9px each (8px glyph + 1px gap).
# 10 + 6*9 = 64px exactly.
HEADER_H = 10
ROW_H = 9
MAX_ROWS = 6


def get_font() -> ImageFont.ImageFont:
    global _font_instance
    if _font_instance is None:
        for path in _FONT_PATHS:
            if os.path.exists(path):
                try:
                    _font_instance = ImageFont.truetype(path, _FONT_SIZE)
                    return _font_instance
                except Exception:
                    pass
        _font_instance = ImageFont.load_default()
    return _font_instance


def text_w(s: str) -> int:
    f = get_font()
    try:
        return int(f.getlength(s))
    except AttributeError:
        return len(s) * 6


def render_header(
    draw: ImageDraw.ImageDraw, img_w: int, title: str, n: int, total: int
) -> None:
    draw.rectangle([0, 0, img_w - 1, HEADER_H - 1], fill=1)
    indicator = f"{n}/{total}"
    draw.text((2, 1), title, font=get_font(), fill=0)
    draw.text((img_w - text_w(indicator) - 2, 1), indicator, font=get_font(), fill=0)


def row_y(row: int) -> int:
    return HEADER_H + 1 + row * ROW_H


def render_row(
    draw: ImageDraw.ImageDraw, row: int, txt: str, x: int = 2, fill: int = 1
) -> None:
    draw.text((x, row_y(row)), txt, font=get_font(), fill=fill)


def render_pair(
    draw: ImageDraw.ImageDraw, row: int, left: str, right: str, img_w: int = 256
) -> None:
    render_row(draw, row, left, x=2)
    render_row(draw, row, right, x=img_w // 2 + 2)


class BaseScreen:
    title: str = "SCREEN"

    def get_title(self, data: dict) -> str:
        return self.title

    def render(self, img: Image.Image, data: dict, n: int, total: int) -> None:
        draw = ImageDraw.Draw(img)
        render_header(draw, img.width, self.get_title(data), n, total)
        self.draw_content(draw, img, data)

    def draw_content(
        self, draw: ImageDraw.ImageDraw, img: Image.Image, data: dict
    ) -> None:
        pass

    def no_data(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        render_row(draw, 2, "Awaiting data...", x=img.width // 4)
