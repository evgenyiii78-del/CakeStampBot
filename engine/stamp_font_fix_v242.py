"""CakeStampBot v2.4.2 font fix.

Comic Sans MS and GOST Type A are traced from their real TTF contours, but the
stamp relief is a thin selectable-width contour instead of a filled glyph.
This preserves the actual font silhouette while keeping practical 0.35-0.60 mm
stamp lines and much lighter geometry than v2.4.1 filled TTF relief.
"""
from __future__ import annotations

import math
import threading
from pathlib import Path

import trimesh
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

from .common import export_bundle, extrude_shape, heart_mesh, parse_size
from .ttf_vector_engine import text_to_ttf_geometry

_TTF_CONTOUR_FONTS = {"comic", "gost"}
_BUILD_LOCK = threading.RLock()


def _poly_parts(shape):
    if shape is None or shape.is_empty:
        return []
    if isinstance(shape, Polygon):
        return [shape]
    if isinstance(shape, MultiPolygon):
        return [p for p in shape.geoms if not p.is_empty]
    out = []
    for g in getattr(shape, "geoms", []):
        if isinstance(g, Polygon) and not g.is_empty:
            out.append(g)
        elif isinstance(g, MultiPolygon):
            out.extend(p for p in g.geoms if not p.is_empty)
    return out


def _center_shape(shape):
    if shape is None or shape.is_empty:
        return shape
    x0, y0, x1, y1 = shape.bounds
    return affinity.translate(shape, xoff=-(x0 + x1) / 2.0, yoff=-(y0 + y1) / 2.0)


def _warp_native_shape(shape, diameter, mode):
    if mode == "normal" or shape is None or shape.is_empty:
        return shape
    x0, y0, x1, y1 = shape.bounds
    width = max(x1 - x0, 1e-6)
    radius = max(10.0, float(diameter) * .39)
    span = math.radians(330.0) if mode == "full" else min(
        math.radians(160.0), max(math.radians(80.0), width / radius)
    )
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    def wp(pt):
        x, y = float(pt[0]), float(pt[1])
        t = (x - cx) / width
        if mode == "bottom":
            a = -math.pi / 2.0 + t * span
            rr = radius - (y - cy)
        else:
            a = math.pi / 2.0 - t * span
            rr = radius + (y - cy)
        return (rr * math.cos(a), rr * math.sin(a))

    warped = []
    for poly in _poly_parts(shape):
        try:
            ext = [wp(p) for p in poly.exterior.coords]
            holes = [[wp(p) for p in ring.coords] for ring in poly.interiors]
            p = Polygon(ext, holes)
            if not p.is_valid:
                p = p.buffer(0)
            warped.extend(_poly_parts(p))
        except Exception:
            continue
    if not warped:
        raise RuntimeError("Не удалось изогнуть TTF-геометрию текста.")
    return unary_union(warped).buffer(0)


def _ttf_contour_stroke(shape, line_width):
    """Trace exact outer/inner TTF contours with a thin printable stroke."""
    width = max(.25, min(.80, float(line_width)))
    half = width / 2.0
    rings = []
    for poly in _poly_parts(shape):
        try:
            ext = LineString(poly.exterior.coords)
            if ext.length > .05:
                rings.append(ext)
            for ring in poly.interiors:
                ln = LineString(ring.coords)
                if ln.length > .05:
                    rings.append(ln)
        except Exception:
            continue
    if not rings:
        raise RuntimeError("Контуры TTF-шрифта пусты.")

    strokes = []
    for ln in rings:
        try:
            s = ln.buffer(half, cap_style=1, join_style=1, resolution=8)
            if s is not None and not s.is_empty:
                strokes.append(s)
        except Exception:
            continue
    if not strokes:
        raise RuntimeError("Не удалось построить тонкий TTF-контур.")

    out = unary_union(strokes).buffer(0)
    # 0.012 mm is far below FDM resolution but removes thousands of redundant
    # vertices produced by the font curves, keeping Telegram 3MF uploads small.
    try:
        out = out.simplify(.012, preserve_topology=True).buffer(0)
    except Exception:
        pass
    return out


def _base_mesh(base_shape, nominal, rw, rh, base_h):
    if base_shape == "rect":
        m = trimesh.creation.box(extents=[float(rw), float(rh), float(base_h)])
        m.apply_translation([0.0, 0.0, float(base_h) / 2.0])
    else:
        m = trimesh.creation.cylinder(
            radius=float(nominal) / 2.0,
            height=float(base_h),
            sections=192,
        )
        m.apply_translation([0.0, 0.0, float(base_h) / 2.0])
    m.metadata["name"] = "Base"
    return m


def _draw_shape(d, shape, xy, fill, hole_fill):
    for p in _poly_parts(shape):
        d.polygon([xy(x, y) for x, y in p.exterior.coords], fill=fill)
        for ring in p.interiors:
            d.polygon([xy(x, y) for x, y in ring.coords], fill=hole_fill)


def _make_preview(engine, path, base_shape, nominal, rw, rh, relief_shape, note, add_crown=False):
    out = int(getattr(engine, "PREVIEW_SIZE", 1400))
    ss = int(getattr(engine, "PREVIEW_SS", 3))
    W = H = out * ss
    pad = 95 * ss
    base_fill = (232, 195, 121)
    relief_fill = (25, 92, 58)
    img = Image.new("RGB", (W, H), (246, 243, 235))
    d = ImageDraw.Draw(img)
    sx = nominal if base_shape != "rect" else rw
    sy = nominal if base_shape != "rect" else rh
    scale = min((W - 2 * pad) / float(sx), (H - 2 * pad) / float(sy))

    def xy(x, y):
        return (W / 2.0 + float(x) * scale, H / 2.0 - float(y) * scale)

    ow = 5 * ss
    if base_shape == "rect":
        x0, y0 = xy(-rw / 2.0, rh / 2.0)
        x1, y1 = xy(rw / 2.0, -rh / 2.0)
        d.rounded_rectangle((x0, y0, x1, y1), radius=24 * ss,
                            fill=base_fill, outline=(135, 91, 38), width=ow)
    else:
        x0, y0 = xy(-nominal / 2.0, nominal / 2.0)
        x1, y1 = xy(nominal / 2.0, -nominal / 2.0)
        d.ellipse((x0, y0, x1, y1), fill=base_fill,
                  outline=(135, 91, 38), width=ow)

    _draw_shape(d, relief_shape, xy, relief_fill, base_fill)
    if add_crown:
        pw = max(3 * ss, int(round(.45 * scale)))
        for pts in engine._crown_preview_paths(nominal, base_shape):
            if len(pts) >= 2:
                d.line([xy(x, y) for x, y in pts], fill=relief_fill, width=pw, joint="curve")

    d.text((100 * ss, 45 * ss), f"CakeStampBot · Thin TTF · {note}", fill=(35, 35, 35))
    img.resize((out, out), Image.Resampling.LANCZOS).save(path, optimize=True)


def _build_ttf_contour_stamp(
    engine, *, text, output_dir, base_size="105", base_shape="round",
    line_width=.45, font_choice="comic", text_path="normal", text_size_mm=12.0,
    add_heart=False, add_crown=False, layout_mode="assembled",
):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    nominal, rw, rh = parse_size(base_size, base_shape)
    mode = str(text_path or "normal").lower()
    mode = mode if mode in {"normal", "top", "bottom", "full"} else "normal"
    mode = "normal" if base_shape != "round" else mode

    safe_w = max(10.0, float(rw if base_shape == "rect" else nominal) - 2.0 * float(engine.SAFE_MARGIN_MM))
    safe_h = max(10.0, float(rh if base_shape == "rect" else nominal) - 2.0 * float(engine.SAFE_MARGIN_MM))
    if add_crown and mode == "normal":
        safe_h = max(10.0, safe_h - min(18.0, float(nominal) * .20))

    requested_size = max(8.0, min(24.0, float(text_size_mm)))
    line_count = max(1, len(str(text or "").splitlines()))
    requested_block_h = requested_size * (1.0 + max(0, line_count - 1) * .90)
    target_h = min(safe_h, requested_block_h)

    # 24 curve steps preserve the real Comic/GOST silhouette while avoiding the
    # huge meshes produced by v2.4.1's 64-step filled glyphs.
    ttf = text_to_ttf_geometry(
        text,
        fonts_dir=Path(engine.__file__).resolve().parent.parent / "fonts",
        font_choice=font_choice,
        target_width_mm=max(8.0, safe_w),
        target_height_mm=max(8.0, target_h),
        line_spacing=.86,
        curve_steps=24,
    )
    native = _center_shape(ttf.geometry)
    if add_crown and mode == "normal":
        native = affinity.translate(native, yoff=-min(6.0, float(nominal) * .055))
    if mode != "normal":
        native = _warp_native_shape(native, nominal, mode)

    relief_shape = _ttf_contour_stroke(native, line_width)
    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Тонкий контур текста пуст.")

    safe_name = engine._se._safe_text_filename(text)
    base_stl = output / f"{safe_name}_TTFContour_Base.stl"
    relief_stl = output / f"{safe_name}_TTFContour_Relief.stl"
    base = _base_mesh(base_shape, nominal, rw, rh, engine.BASE_H)
    relief = extrude_shape(relief_shape, engine.RELIEF_H, "Relief_TTFContour")
    base.export(str(base_stl))
    relief.export(str(relief_stl))

    scene = trimesh.Scene()
    scene.add_geometry(base.copy(), geom_name="Base", node_name="Base")
    r = relief.copy()
    r.apply_translation([0, 0, engine.BASE_H])
    scene.add_geometry(r, geom_name="Relief_TTFContour", node_name="Relief_TTFContour")
    stls = [str(base_stl), str(relief_stl)]

    if add_heart:
        heart = heart_mesh(max(.35, float(line_width)), engine.RELIEF_H, -float(nominal) * .30)
        h = heart.copy(); h.apply_translation([0, 0, engine.BASE_H])
        scene.add_geometry(h, geom_name="Heart", node_name="Heart")
        heart_stl = output / f"{safe_name}_Heart.stl"
        heart.export(str(heart_stl)); stls.append(str(heart_stl))

    if add_crown:
        cw = min(30.0, float(nominal) * .31)
        cy = float(nominal) * .31 if base_shape != "rect" else float(rh) * .30
        crown = engine._crown_mesh(max(.40, float(line_width)), engine.RELIEF_H, cy, width=cw, height_mm=cw * .54)
        cr = crown.copy(); cr.apply_translation([0, 0, engine.BASE_H])
        scene.add_geometry(cr, geom_name="Crown", node_name="Crown")
        crown_stl = output / f"{safe_name}_Crown.stl"
        crown.export(str(crown_stl)); stls.append(str(crown_stl))

    preview = output / f"{safe_name}_ttf_contour_preview.png"
    _make_preview(engine, preview, base_shape, nominal, rw, rh, relief_shape,
                  f"{font_choice} · {float(line_width):.2f} mm · {mode}", add_crown=add_crown)

    meta = {
        "engine": "ttf_contour_stamp_v242",
        "font_choice": font_choice,
        "font_path": ttf.font_path,
        "text_geometry_mode": "true_ttf_contour_thin_stroke",
        "line_width_mm": float(line_width),
        "base_shape": base_shape,
        "base_size": base_size,
        "base_height_mm": engine.BASE_H,
        "relief_height_mm": engine.RELIEF_H,
        "requested_text_height_mm": requested_size,
        "safe_margin_mm": engine.SAFE_MARGIN_MM,
        "text_path": mode,
        "add_heart": bool(add_heart),
        "add_crown": bool(add_crown),
        "layout_mode": layout_mode,
        "curve_steps": 24,
    }
    suffix = "TTF_CONTOUR_STAMP_SEPARATE" if layout_mode == "separate" else "TTF_CONTOUR_STAMP_ASSEMBLED"
    return export_bundle(output, safe_name, scene, str(preview), stls, meta, suffix)


def apply_fixes(engine):
    original_build = engine.build_stamp_from_text_blender

    def build_stamp_from_text_blender(
        *, text, output_dir, base_size="105", base_shape="round", line_width=.45,
        font_choice="classic", text_path="normal", text_size_mm=12.0,
        add_heart=False, add_crown=False, layout_mode="assembled",
    ):
        choice = str(font_choice or "classic").lower()
        width = max(.25, min(.80, float(line_width)))
        if choice in _TTF_CONTOUR_FONTS:
            return _build_ttf_contour_stamp(
                engine,
                text=text, output_dir=output_dir, base_size=base_size,
                base_shape=base_shape, line_width=width, font_choice=choice,
                text_path=text_path, text_size_mm=text_size_mm,
                add_heart=add_heart, add_crown=add_crown,
                layout_mode=layout_mode,
            )

        # Classic keeps the proven centerline engine but must honor the selected width.
        with _BUILD_LOCK:
            old_width = engine.LINE_WIDTH_MM
            engine.LINE_WIDTH_MM = width
            try:
                return original_build(
                    text=text, output_dir=output_dir, base_size=base_size,
                    base_shape=base_shape, line_width=width, font_choice=choice,
                    text_path=text_path, text_size_mm=text_size_mm,
                    add_heart=add_heart, add_crown=add_crown,
                    layout_mode=layout_mode,
                )
            finally:
                engine.LINE_WIDTH_MM = old_width

    engine.build_stamp_from_text_blender = build_stamp_from_text_blender
