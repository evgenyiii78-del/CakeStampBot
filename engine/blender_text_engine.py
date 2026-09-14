"""Experimental Blender text engine for CakeStampBot v2.0.2-alpha.

Only straight text stamps are handled here for the first test. The existing
stamp_v172 engine remains the fallback for unsupported modes or Blender errors.
This revision keeps model geometry/layout unchanged and improves preview
anti-aliasing using supersampling + LANCZOS downsampling.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, GeometryCollection

from .common import export_bundle, heart_mesh, mask_to_centerline_line, parse_size
from . import stamp_engine as _se
from .ttf_vector_engine import text_to_ttf_geometry

logger = logging.getLogger("CakeStampEngine.BlenderText")

BASE_H = 0.6
RELIEF_H = 6.5
SAFE_MARGIN_MM = 15.0
LINE_WIDTH_MM = 0.25
CENTERLINE_PPM = 96
RESAMPLE_STEP_MM = 0.025
PREVIEW_SIZE = 1400
PREVIEW_SS = 3


def blender_binary() -> str | None:
    configured = os.getenv("BLENDER_BIN", "").strip()
    if configured and Path(configured).exists():
        return configured
    return shutil.which("blender")


def blender_available() -> bool:
    return bool(blender_binary())


def _line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if not g.is_empty]
    if isinstance(geom, GeometryCollection) or hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            if isinstance(g, LineString) and not g.is_empty:
                out.append(g)
            elif isinstance(g, MultiLineString):
                out.extend(x for x in g.geoms if not x.is_empty)
        return out
    return []


def _outline_to_centerline(outline_shape, ppm: int = CENTERLINE_PPM):
    if outline_shape is None or outline_shape.is_empty:
        raise RuntimeError("Пустая TTF-геометрия для Blender engine.")

    from PIL import Image as PILImage, ImageDraw as PILImageDraw

    minx, miny, maxx, maxy = outline_shape.bounds
    pad_mm = 2.0
    ppm = int(max(72, min(120, ppm)))
    width_px = max(128, int(round((maxx - minx + 2 * pad_mm) * ppm)))
    height_px = max(128, int(round((maxy - miny + 2 * pad_mm) * ppm)))

    mask = PILImage.new("L", (width_px, height_px), 0)
    draw = PILImageDraw.Draw(mask)

    def xy(x, y):
        return ((x - minx + pad_mm) * ppm, (maxy - y + pad_mm) * ppm)

    if outline_shape.geom_type == "Polygon":
        polys = [outline_shape]
    elif outline_shape.geom_type == "MultiPolygon":
        polys = list(outline_shape.geoms)
    else:
        polys = [g for g in getattr(outline_shape, "geoms", []) if g.geom_type == "Polygon"]

    for poly in polys:
        draw.polygon([xy(x, y) for x, y in poly.exterior.coords], fill=255)
        for ring in poly.interiors:
            draw.polygon([xy(x, y) for x, y in ring.coords], fill=0)

    centerline = mask_to_centerline_line(mask, ppm)
    if centerline is None or centerline.is_empty:
        raise RuntimeError("Blender engine: не удалось получить centerline.")

    bx0, by0, bx1, by1 = centerline.bounds
    centerline = affinity.translate(
        centerline,
        xoff=-(bx0 + bx1) / 2.0,
        yoff=-(by0 + by1) / 2.0,
    )
    centerline = _se._remove_tiny_centerline_parts(centerline, min_length_mm=0.18)
    centerline = _se._prune_short_terminal_spurs(centerline, max_spur_mm=0.48)
    centerline = _se._smooth_text_centerlines(centerline)
    centerline = _se._remove_tiny_centerline_parts(centerline, min_length_mm=0.18)
    centerline = _se._prune_short_terminal_spurs(centerline, max_spur_mm=0.34)
    return centerline


def _fit_centerline(geom, max_w: float, max_h: float):
    minx, miny, maxx, maxy = geom.bounds
    w = max(maxx - minx, 1e-9)
    h = max(maxy - miny, 1e-9)
    factor = min(float(max_w) / w, float(max_h) / h)
    geom = affinity.scale(geom, xfact=factor, yfact=factor, origin=(0.0, 0.0))
    try:
        geom = _se._smooth_text_centerlines(geom)
    except Exception:
        pass
    bx0, by0, bx1, by1 = geom.bounds
    return affinity.translate(
        geom,
        xoff=-(bx0 + bx1) / 2.0,
        yoff=-(by0 + by1) / 2.0,
    )


def _resample_path(line: LineString, step: float = RESAMPLE_STEP_MM):
    if line.length <= step:
        return [(float(x), float(y)) for x, y in line.coords]
    n = max(8, int(math.ceil(line.length / step)) + 1)
    ds = np.linspace(0.0, float(line.length), n)
    pts = [line.interpolate(float(d)) for d in ds]
    return [(float(p.x), float(p.y)) for p in pts]


def _make_preview(path: Path, base_shape: str, nominal: float, rw: float, rh: float, paths):
    """High quality preview only. Does not change 3MF geometry."""
    out_w = out_h = PREVIEW_SIZE
    ss = PREVIEW_SS
    W = out_w * ss
    H = out_h * ss
    pad = 95 * ss

    img = Image.new("RGB", (W, H), (246, 243, 235))
    draw = ImageDraw.Draw(img)

    span_x = nominal if base_shape != "rect" else rw
    span_y = nominal if base_shape != "rect" else rh
    scale = min((W - 2 * pad) / span_x, (H - 2 * pad) / span_y)

    def xy(x, y):
        return (W / 2 + x * scale, H / 2 - y * scale)

    outline_w = max(2 * ss, 5 * ss)
    if base_shape == "rect":
        x0, y0 = xy(-rw / 2, rh / 2)
        x1, y1 = xy(rw / 2, -rh / 2)
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=24 * ss,
            fill=(232, 195, 121),
            outline=(135, 91, 38),
            width=outline_w,
        )
    else:
        x0, y0 = xy(-nominal / 2, nominal / 2)
        x1, y1 = xy(nominal / 2, -nominal / 2)
        draw.ellipse(
            (x0, y0, x1, y1),
            fill=(232, 195, 121),
            outline=(135, 91, 38),
            width=outline_w,
        )

    px_width = max(3 * ss, int(round(LINE_WIDTH_MM * scale)))
    for pts in paths:
        if len(pts) >= 2:
            screen_pts = [xy(x, y) for x, y in pts]
            draw.line(
                screen_pts,
                fill=(25, 92, 58),
                width=px_width,
                joint="curve",
            )
            # Round terminal caps in the preview so zoomed Telegram images do
            # not show square/pixel-stepped ends.
            r = px_width / 2.0
            for ex, ey in (screen_pts[0], screen_pts[-1]):
                draw.ellipse((ex-r, ey-r, ex+r, ey+r), fill=(25, 92, 58))

    draw.text((100 * ss, 45 * ss), "CakeStampBot v2.0.2-alpha · AA Preview", fill=(35, 35, 35))

    img = img.resize((out_w, out_h), Image.Resampling.LANCZOS)
    img.save(path, optimize=True)


def build_stamp_from_text_blender(*, text, output_dir, base_size="105", base_shape="round",
                                  line_width=0.25, font_choice="classic", text_path="normal",
                                  text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    if str(text_path or "normal").lower() != "normal":
        raise NotImplementedError("Blender alpha пока поддерживает только обычный прямой текст.")

    blender = blender_binary()
    if not blender:
        raise RuntimeError("Blender executable not found")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    nominal, rw, rh = parse_size(base_size, base_shape)
    safe_w = max(10.0, float(rw if base_shape == "rect" else nominal) - 2 * SAFE_MARGIN_MM)
    safe_h = max(10.0, float(rh if base_shape == "rect" else nominal) - 2 * SAFE_MARGIN_MM)

    ttf = text_to_ttf_geometry(
        text,
        fonts_dir=Path(__file__).resolve().parent.parent / "fonts",
        font_choice=font_choice,
        target_width_mm=max(8.0, safe_w),
        target_height_mm=max(8.0, safe_h),
        line_spacing=0.86,
        curve_steps=48,
    )
    centerline = _outline_to_centerline(ttf.geometry, CENTERLINE_PPM)
    centerline = _fit_centerline(centerline, safe_w, safe_h)

    paths = []
    for line in _line_parts(centerline):
        pts = _resample_path(line)
        if len(pts) >= 2:
            paths.append(pts)
    if not paths:
        raise RuntimeError("Blender engine: centerline paths are empty")

    safe_name = _se._safe_text_filename(text)
    job_path = output / f"{safe_name}_blender_job.json"
    base_stl = output / f"{safe_name}_Blender_Base.stl"
    relief_stl = output / f"{safe_name}_Blender_Relief.stl"

    job = {
        "base_shape": base_shape,
        "nominal": float(nominal),
        "rect_w": float(rw),
        "rect_h": float(rh),
        "base_height": BASE_H,
        "relief_height": RELIEF_H,
        "line_width": LINE_WIDTH_MM,
        "paths": paths,
        "base_stl": str(base_stl),
        "relief_stl": str(relief_stl),
    }
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")

    script = Path(__file__).resolve().parent.parent / "scripts" / "blender_generate_stamp.py"
    cmd = [blender, "-b", "--python", str(script), "--", "--job", str(job_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    if proc.returncode != 0:
        logger.error("Blender failed:\n%s", proc.stdout[-6000:])
        raise RuntimeError(f"Blender завершился с кодом {proc.returncode}")
    if not base_stl.exists() or not relief_stl.exists():
        raise RuntimeError("Blender не создал STL-файлы")

    base = trimesh.load(str(base_stl), force="mesh")
    relief = trimesh.load(str(relief_stl), force="mesh")
    base.metadata["name"] = "BlenderBase"
    relief.metadata["name"] = "BlenderRelief"

    scene = trimesh.Scene()
    scene.add_geometry(base.copy(), geom_name="Base", node_name="Base")
    r = relief.copy()
    r.apply_translation([0, 0, BASE_H])
    scene.add_geometry(r, geom_name="Relief_Blender", node_name="Relief_Blender")

    stls = [str(base_stl), str(relief_stl)]
    if add_heart:
        heart = heart_mesh(0.35, RELIEF_H, -nominal * 0.30)
        h = heart.copy()
        h.apply_translation([0, 0, BASE_H])
        scene.add_geometry(h, geom_name="Heart", node_name="Heart")
        heart_stl = output / f"{safe_name}_Heart.stl"
        heart.export(str(heart_stl))
        stls.append(str(heart_stl))

    preview_png = output / f"{safe_name}_blender_preview.png"
    _make_preview(preview_png, base_shape, nominal, rw, rh, paths)

    meta = {
        "version": "2.0.2-alpha",
        "engine": "blender_text_ribbon_smooth",
        "font_choice": font_choice,
        "font_path": ttf.font_path,
        "base_shape": base_shape,
        "base_size": base_size,
        "base_height_mm": BASE_H,
        "relief_height_mm": RELIEF_H,
        "line_width_mm": LINE_WIDTH_MM,
        "safe_margin_mm": SAFE_MARGIN_MM,
        "centerline_ppm": CENTERLINE_PPM,
        "resample_step_mm": RESAMPLE_STEP_MM,
        "preview_supersampling": PREVIEW_SS,
        "text_path": "normal",
        "layout_mode": layout_mode,
    }
    suffix = "BLENDER_ALPHA_SEPARATE" if layout_mode == "separate" else "BLENDER_ALPHA_ASSEMBLED"
    return export_bundle(output, safe_name, scene, str(preview_png), stls, meta, suffix)
