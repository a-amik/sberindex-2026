"""Маленький рисовальщик SVG для колоды.

Цвета задаются переменными кита (var(--c-all), var(--text-3)…): график,
вставленный в слайд, перекрашивается вместе со сценой — тёмной для показа
и светлой для печати.
"""
from __future__ import annotations

from html import escape


def nice(v: float) -> str:
    """Число по-русски: пробел в тысячах, запятая в дробях."""
    if abs(v) >= 1000 or float(v).is_integer():
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:.1f}".replace(".", ",")


FONT_SCALE = 1.3     # графики стоят на холсте 1600 × 900 и ужимаются в колонку: кегль крупнее, чем на листе


class Svg:
    def __init__(self, w: int, h: int, cls: str = "fig"):
        self.w, self.h, self.items = w, h, []
        self.cls = cls

    def add(self, s: str):
        self.items.append(s)
        return self

    def line(self, x1, y1, x2, y2, stroke="var(--line-2)", w=1, dash=None, cap="round"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
                        f'stroke-width="{w}" stroke-linecap="{cap}"{d}/>')

    def rect(self, x, y, w, h, fill, r=4, op=1.0):
        return self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" '
                        f'rx="{r}" fill="{fill}" fill-opacity="{op}"/>')

    def circle(self, x, y, r, fill, op=1.0, stroke=None):
        s = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
        return self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" fill-opacity="{op}"{s}/>')

    def path(self, pts, stroke, w=2.5, dash=None, fill="none", op=1.0):
        if not pts:
            return self
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if fill != "none":
            d += " Z"
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        return self.add(f'<path d="{d}" fill="{fill}" fill-opacity="{op}" stroke="{stroke}" stroke-width="{w}" '
                        f'stroke-linejoin="round" stroke-linecap="round"{ds}/>')

    def text(self, x, y, s, size=18, fill="var(--text-2)", anchor="start", weight=400, cls=""):
        c = f' class="{cls}"' if cls else ""
        size = round(size * FONT_SCALE)
        return self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
                        f'font-weight="{weight}"{c}>{escape(str(s))}</text>')

    def render(self) -> str:
        return (f'<svg class="{self.cls}" viewBox="0 0 {self.w} {self.h}" xmlns="http://www.w3.org/2000/svg" '
                f'role="img" font-family="var(--font)" style="font-variant-numeric: tabular-nums">'
                + "".join(self.items) + "</svg>")


def scale(v0, v1, p0, p1):
    k = (p1 - p0) / ((v1 - v0) or 1)
    return lambda v: p0 + (v - v0) * k
