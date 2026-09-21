"""CakeStampBot v2.4.3 font fix.

Comic Sans MS and GOST Type A are converted from their real filled TTF glyphs
to a high-resolution medial-axis centerline. The stamp therefore has ONE
printable line through each original font stroke instead of tracing both glyph
edges. Only a tiny pixel-level simplify is applied: no aggressive pruning or
multi-pass smoothing that can turn Comic Sans into a generic sans shape.
"""
from __future__ import annotations

import math
import threading
from pathlib import Path

import trimesh
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from shapely.ops import unary_union

from .common import export_bundle, extrude_shape, heart_mesh, parse_size
from .ttf_vector_engine import text_to_ttf_geometry

_SINGLE_LINE_TTF_FONTS = {"comic", "gost"}
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


def _line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if not g.is_empty]
    out = []
    for g in getattr(geom, "geoms", []):
        if isinstance(g, LineString) and not g.is_empty:
            out.append(g)
        elif isinstance(g, MultiLineString):
            out.extend(x for x in g.geoms if not x.is_empty)
    return out


def _ttf_medial_axis(engine, shape):
    """Rasterize true TTF fill and recover one centerline per physical stroke."""
    if shape is None or shape.is_empty:
        raise RuntimeError("Пустая TTF-геометрия.")

    minx, miny, maxx, maxy = shape.bounds
    pad = 1.5
    ppm = 72
    w_mm = maxx - minx + 2 * pad
    h_mm = maxy - miny + 2 * pad
    W = max(128, int(round(w_mm * ppm)))
    H = max(128, int(round(h_mm * ppm)))

    # Keep memory/time bounded on long inscriptions while staying well above
    # the practical FDM resolution of a 0.35 mm relief line.
    max_pixels = 11_000_000
    if W * H > max_pixels:
        scale = math.sqrt(max_pixels / float(W * H))
        ppm = max(48, int(ppm * scale))
        W = max(128, int(round(w_mm * ppm)))
        H = max(128, int(round(h_mm * ppm)))

    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)

    def xy(x, y):
        return ((x - minx + pad) * ppm, (maxy - y + pad) * ppm)

    for poly in _poly_parts(shape):
        draw.polygon([xy(x, y) for x, y in poly.exterior.coords], fill=255)
        for ring in poly.interiors:
            draw.polygon([xy(x, y) for x, y in ring.coords], fill=0)

    center = engine.mask_to_centerline_line(mask, ppm)
    if center is None or center.is_empty:
        raise RuntimeError("Не удалось получить осевую линию TTF-шрифта.")

    # mask_to_centerline_line is centered on the raster canvas. Restore the
    # original TTF block position (important when crown layout shifts text).
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    center = affinity.translate(center, xoff=cx, yoff=cy)

    # Preserve font character. Remove only sub-pixel/tiny fragments and a
    # one-pixel staircase. No spur pruning and no repeated Chaikin smoothing.
    parts = []
    for line in _line_parts(center):
        if line.length < .10:
            continue
        try:
            line = line.simplify(max(.006, 0.55 / ppm), preserve_topology=False)
        except Exception:
            pass
        if line is not None and not line.is_empty and line.length >= .10:
            parts.append(line)

    if not parts:
        raise RuntimeError("Осевая линия TTF пуста после очистки.")
    return unary_union(parts)


def _stroke_centerline(centerline, line_width):
    width = max(.25, min(.80, float(line_width)))
    pieces = []
    for line in _line_parts(centerline):
        if line.length < .10:
            continue
        try:
            poly = line.buffer(width / 2.0, cap_style=1, join_style=1, resolution=12)
            if poly is not None and not poly.is_empty:
                pieces.append(poly)
        except Exception:
            continue
    if not pieces:
        raise RuntimeError("Не удалось построить single-line рельеф текста.")
    out = unary_union(pieces).buffer(0)
    try:
        out = out.simplify(.006, preserve_topology=True).buffer(0)
    except Exception:
        pass
    return out


def _base_mesh(base_shape, nominal, rw, rh, base_h):
    if base_shape == "rect":
        mesh = trimesh.creation.box(extents=[float(rw), float(rh), float(base_h)])
        mesh.apply_translation([0.0, 0.0, float(base_h) / 2.0])
    else:
        mesh = trimesh.creation.cylinder(
            radius=float(nominal) / 2.0,
            height=float(base_h),
            sections=192,
        )
        mesh.apply_translation([0.0, 0.0, float(base_h) / 2.0])
    mesh.metadata["name"] = "Base"
    return mesh


def _draw_shape(draw, shape, xy, fill, hole_fill):
    for poly in _poly_parts(shape):
        draw.polygon([xy(x, y) for x, y in poly.exterior.coords], fill=fill)
        for ring in poly.interiors:
            draw.polygon([xy(x, y) for x, y in ring.coords], fill=hole_fill)


def _make_preview(engine, path, base_shape, nominal, rw, rh, relief_shape, note, add_crown=False):
    out = int(getattr(engine, "PREVIEW_SIZE", 1400))
    ss = int(getattr(engine, "PREVIEW_SS", 3))
    W = H = out * ss
    pad = 95 * ss
    base_fill = (232, 195, 121)
    relief_fill = (25, 92, 58)
    img = Image.new("RGB", (W, H), (246, 243, 235))
    draw = ImageDraw.Draw(img)
    sx = nominal if base_shape != "rect" else rw
    sy = nominal if base_shape != "rect" else rh
    scale = min((W - 2 * pad) / float(sx), (H - 2 * pad) / float(sy))

    def xy(x, y):
        return (W / 2.0 + float(x) * scale, H / 2.0 - float(y) * scale)

    ow = 5 * ss
    if base_shape == "rect":
        x0, y0 = xy(-rw / 2.0, rh / 2.0)
        x1, y1 = xy(rw / 2.0, -rh / 2.0)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=24 * ss,
                               fill=base_fill, outline=(135, 91, 38), width=ow)
    else:
        x0, y0 = xy(-nominal / 2.0, nominal / 2.0)
        x1, y1 = xy(nominal / 2.0, -nominal / 2.0)
        draw.ellipse((x0, y0, x1, y1), fill=base_fill,
                     outline=(135, 91, 38), width=ow)

    _draw_shape(draw, relief_shape, xy, relief_fill, base_fill)
    if add_crown:
        pw = max(3 * ss, int(round(.45 * scale)))
        for pts in engine._crown_preview_paths(nominal, base_shape):
            if len(pts) >= 2:
                draw.line([xy(x, y) for x, y in pts], fill=relief_fill, width=pw, joint="curve")

    draw.text((100 * ss, 45 * ss), f"CakeStampBot · TTF Single Line · {note}", fill=(35, 35, 35))
    img.resize((out, out), Image.Resampling.LANCZOS).save(path, optimize=True)


def _build_single_line_ttf_stamp(
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

    ttf = text_to_ttf_geometry(
        text,
        fonts_dir=Path(engine.__file__).resolve().parent.parent / "fonts",
        font_choice=font_choice,
        target_width_mm=max(8.0, safe_w),
        target_height_mm=max(8.0, target_h),
        line_spacing=.86,
        curve_steps=32,
    )

    centerline = _ttf_medial_axis(engine, ttf.geometry)
    if add_crown and mode == "normal":
        centerline = affinity.translate(centerline, yoff=-min(6.0, float(nominal) * .055))
    if mode != "normal":
        centerline = engine._warp_centerline(centerline, nominal, mode)

    relief_shape = _stroke_centerline(centerline, line_width)
    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Single-line TTF рельеф пуст.")

    safe_name = engine._se._safe_text_filename(text)
    base_stl = output / f"{safe_name}_TTFSingleLine_Base.stl"
    relief_stl = output / f"{safe_name}_TTFSingleLine_Relief.stl"
    base = _base_mesh(base_shape, nominal, rw, rh, engine.BASE_H)
    relief = extrude_shape(relief_shape, engine.RELIEF_H, "Relief_TTFSingleLine")
    base.export(str(base_stl))
    relief.export(str(relief_stl))

    scene = trimesh.Scene()
    scene.add_geometry(base.copy(), geom_name="Base", node_name="Base")
    r = relief.copy(); r.apply_translation([0, 0, engine.BASE_H])
    scene.add_geometry(r, geom_name="Relief_TTFSingleLine", node_name="Relief_TTFSingleLine")
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

    preview = output / f"{safe_name}_ttf_singleline_preview.png"
    _make_preview(engine, preview, base_shape, nominal, rw, rh, relief_shape,
                  f"{font_choice} · {float(line_width):.2f} mm · {mode}", add_crown=add_crown)

    meta = {
        "engine": "ttf_single_line_stamp_v243",
        "font_choice": font_choice,
        "font_path": ttf.font_path,
        "text_geometry_mode": "true_ttf_fill_to_medial_axis_single_line",
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
        "curve_steps": 32,
        "medial_axis_ppm": 72,
        "aggressive_pruning": False,
        "aggressive_smoothing": False,
    }
    suffix = "TTF_SINGLELINE_STAMP_SEPARATE" if layout_mode == "separate" else "TTF_SINGLELINE_STAMP_ASSEMBLED"
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
        if choice in _SINGLE_LINE_TTF_FONTS:
            return _build_single_line_ttf_stamp(
                engine,
                text=text, output_dir=output_dir, base_size=base_size,
                base_shape=base_shape, line_width=width, font_choice=choice,
                text_path=text_path, text_size_mm=text_size_mm,
                add_heart=add_heart, add_crown=add_crown,
                layout_mode=layout_mode,
            )

        # Classic keeps the existing centerline engine and selected width.
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
