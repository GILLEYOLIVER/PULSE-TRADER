"""Small dependency-free antialiased line layer for Tk charts.

Candles and labels remain vector Canvas items; this layer smooths the EMA lines
even in the basic installation, which does not include Pillow.
"""

from __future__ import annotations

import base64
import struct
import zlib


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))


def antialiased_lines_png(width: int, height: int, curves: list[tuple[list[tuple[float, float]], str]]) -> str:
    """Render connected market samples with subpixel coverage as a Tk PNG string."""
    pixels = bytearray(width * height * 4)

    def plot(x: int, y: int, coverage: float, color: tuple[int, int, int]) -> None:
        if not (0 <= x < width and 0 <= y < height):
            return
        coverage = max(0.0, min(1.0, coverage))
        if coverage == 0:
            return
        index = 4 * (y * width + x)
        previous_alpha = pixels[index + 3] / 255
        alpha = coverage + previous_alpha * (1 - coverage)
        for channel in range(3):
            pixels[index + channel] = round(
                (color[channel] * coverage + pixels[index + channel] * previous_alpha * (1 - coverage)) / alpha
            )
        pixels[index + 3] = round(alpha * 255)

    def stroke(a: tuple[float, float], b: tuple[float, float], color: tuple[int, int, int]) -> None:
        x0, y0 = a
        x1, y1 = b
        steep = abs(y1 - y0) > abs(x1 - x0)
        if steep:
            x0, y0, x1, y1 = y0, x0, y1, x1
        if x0 > x1:
            x0, y0, x1, y1 = x1, y1, x0, y0
        dx = x1 - x0
        gradient = (y1 - y0) / dx if dx else 0

        def pair(x: int, y: float, weight: float) -> None:
            floor_y = int(y // 1)
            frac = y - floor_y
            if steep:
                plot(floor_y, x, weight * (1 - frac), color)
                plot(floor_y + 1, x, weight * frac, color)
            else:
                plot(x, floor_y, weight * (1 - frac), color)
                plot(x, floor_y + 1, weight * frac, color)

        first = round(x0)
        last = round(x1)
        if first == last:
            pair(first, (y0 + y1) / 2, 1)
            return
        pair(first, y0 + gradient * (first - x0), 1 - ((x0 + .5) % 1))
        for x in range(first + 1, last):
            pair(x, y0 + gradient * (x - x0), 1)
        pair(last, y0 + gradient * (last - x0), (x1 + .5) % 1)

    for points, hex_color in curves:
        color = tuple(bytes.fromhex(hex_color.lstrip("#")))
        for a, b in zip(points, points[1:]):
            stroke(a, b, color)

    raw = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(raw, 4))
    png += _png_chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")
