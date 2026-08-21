
import logging
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely import affinity

from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen

from .common import find_font_path

logger = logging.getLogger("CakeStampEngine.VectorText")


def _poly_area(points):
    if len(points) < 3:
        return 0.0
    s = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        s += x1 * y2 - x2 * y1
    return 0.5 * s


class _FlattenGlyphPen(BasePen):
    """
    Converts glyph contours to high-resolution point rings.
    We avoid raster text entirely for topper geometry.
    """
    def __init__(self, glyph_set, curve_steps=16):
        super().__init__(glyph_set)
        self.curve_steps = int(curve_steps)
        self.contours = []
        self._current = []
        self._last = None

    def _moveTo(self, p0):
        self._closePath()
        self._current = [(float(p0[0]), float(p0[1]))]
        self._last = (float(p0[0]), float(p0[1]))

    def _lineTo(self, p1):
        p1 = (float(p1[0]), float(p1[1]))
        self._current.append(p1)
        self._last = p1

    def _qCurveToOne(self, p1, p2):
        p0 = self._last
        p1 = (float(p1[0]), float(p1[1]))
        p2 = (float(p2[0]), float(p2[1]))
        if p0 is None:
            self._lineTo(p2)
            return

        for i in range(1, self.curve_steps + 1):
            t = i / self.curve_steps
            mt = 1.0 - t
            x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
            y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
            self._current.append((x, y))
        self._last = p2

    def _curveToOne(self, p1, p2, p3):
        p0 = self._last
        p1 = (float(p1[0]), float(p1[1]))
        p2 = (float(p2[0]), float(p2[1]))
        p3 = (float(p3[0]), float(p3[1]))
        if p0 is None:
            self._lineTo(p3)
            return

        for i in range(1, self.curve_steps + 1):
            t = i / self.curve_steps
            mt = 1.0 - t
            x = (
                mt ** 3 * p0[0]
                + 3 * mt * mt * t * p1[0]
                + 3 * mt * t * t * p2[0]
                + t ** 3 * p3[0]
            )
            y = (
                mt ** 3 * p0[1]
                + 3 * mt * mt * t * p1[1]
                + 3 * mt * t * t * p2[1]
                + t ** 3 * p3[1]
            )
            self._current.append((x, y))
        self._last = p3

    def _closePath(self):
        if self._current and len(self._current) >= 3:
            # Remove near-duplicate closing point.
            if np.linalg.norm(np.array(self._current[0]) - np.array(self._current[-1])) < 1e-6:
                self._current = self._current[:-1]
            if abs(_poly_area(self._current)) > 1e-3:
                self.contours.append(self._current)
        self._current = []
        self._last = None

    def _endPath(self):
        self._closePath()


def _glyph_to_shape(glyph, glyph_set, curve_steps=18):
    pen = _FlattenGlyphPen(glyph_set, curve_steps=min(int(curve_steps), 20))
    glyph.draw(pen)
    pen._closePath()

    result = None
    for contour in pen.contours:
        if len(contour) < 3:
            continue
        poly = Polygon(contour)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            continue

        # Even-odd fill by symmetric difference:
        # outer contour adds material, inner contour removes it.
        result = poly if result is None else result.symmetric_difference(poly)

    if result is None:
        return None

    return result.buffer(0).simplify(0.0008, preserve_topology=True).buffer(0)


@dataclass
class VectorTextResult:
    shape: object
    font_path: str
    width_mm: float
    height_mm: float
    scale: float


def text_to_shape(
    text: str,
    font_choice: str = "classic",
    target_width_mm: float = 110.0,
    target_height_mm: float = 45.0,
    line_spacing: float = 1.05,
    curve_steps: int = 20,
) -> VectorTextResult:
    """
    Convert TTF glyph outlines directly to Shapely polygons in millimeters.

    This is the core rewrite:
    no raster mask, no skeleton, no pixel stair-steps.
    """
    font_path = find_font_path(font_choice)
    font = TTFont(font_path)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    hmtx = font["hmtx"].metrics
    units_per_em = float(font["head"].unitsPerEm)

    lines = str(text or "").splitlines() or [str(text or "")]
    if not any(line.strip() for line in lines):
        raise RuntimeError("Пустой текст для векторной генерации.")

    fallback_glyph = cmap.get(ord("?"), ".notdef")
    space_advance = hmtx.get(cmap.get(ord(" "), "space"), (units_per_em * 0.33, 0))[0]

    line_geoms = []
    line_widths = []

    for line_index, line in enumerate(lines):
        glyph_names = []
        advances = []

        for ch in line:
            if ch == " ":
                glyph_names.append(None)
                advances.append(float(space_advance))
                continue

            gname = cmap.get(ord(ch), fallback_glyph)
            if gname not in glyph_set:
                gname = fallback_glyph
            glyph_names.append(gname)
            advances.append(float(hmtx.get(gname, (units_per_em * 0.55, 0))[0]))

        line_width = sum(advances)
        line_widths.append(line_width)

        x_cursor = -line_width / 2.0
        y_cursor = -line_index * units_per_em * line_spacing
        geoms = []

        for gname, adv in zip(glyph_names, advances):
            if gname is not None:
                glyph = glyph_set[gname]
                gshape = _glyph_to_shape(glyph, glyph_set, curve_steps=min(int(curve_steps), 20))
                if gshape is not None and not gshape.is_empty:
                    geoms.append(affinity.translate(gshape, xoff=x_cursor, yoff=y_cursor))
            x_cursor += adv

        if geoms:
            line_geoms.append(unary_union(geoms).buffer(0))

    if not line_geoms:
        raise RuntimeError("Не удалось построить векторный текст.")

    shape = unary_union(line_geoms).buffer(0)
    minx, miny, maxx, maxy = shape.bounds
    width_units = max(maxx - minx, 1.0)
    height_units = max(maxy - miny, 1.0)

    scale = min(target_width_mm / width_units, target_height_mm / height_units)
    shape = affinity.scale(shape, xfact=scale, yfact=scale, origin=(0, 0))

    minx, miny, maxx, maxy = shape.bounds
    shape = affinity.translate(
        shape,
        xoff=-(minx + maxx) / 2.0,
        yoff=-(miny + maxy) / 2.0,
    ).buffer(0).simplify(0.018, preserve_topology=True).buffer(0)

    minx, miny, maxx, maxy = shape.bounds
    return VectorTextResult(
        shape=shape,
        font_path=font_path,
        width_mm=maxx - minx,
        height_mm=maxy - miny,
        scale=scale,
    )
