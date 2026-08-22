
from pathlib import Path
import logging
import re
import unicodedata
import numpy as np
import trimesh

from shapely.affinity import scale, translate
from shapely.geometry import LineString, MultiLineString, GeometryCollection

from .common import *

logger = logging.getLogger("CakeStampEngine.StampV1_3_0")

PX_TEXT = 120
PX_IMAGE = 36
RELIEF_H = 6.5
BASE_H = 0.7


def _fit_targets(base_size, base_shape):
    nominal, rw, rh = parse_size(base_size, base_shape)
    if base_shape == "rect":
        return nominal, rw, rh, rw * 0.78, rh * 0.56
    return nominal, nominal, nominal, nominal * 0.72, nominal * 0.52


def _fit_line_geometry(line_geom, target_w, target_h, margin_mm=4.0):
    minx, miny, maxx, maxy = line_geom.bounds
    w = max(maxx - minx, 1e-6)
    h = max(maxy - miny, 1e-6)

    sx = max((target_w - margin_mm) / w, 1e-6)
    sy = max((target_h - margin_mm) / h, 1e-6)
    s = min(sx, sy)

    g = scale(line_geom, xfact=s, yfact=s, origin=(0, 0))
    minx, miny, maxx, maxy = g.bounds
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    return translate(g, xoff=-cx, yoff=-cy)


def _chaikin_coords(coords, refinements=4):
    pts = [(float(x), float(y)) for x, y in coords]
    if len(pts) < 3:
        return pts

    for _ in range(refinements):
        if len(pts) < 3:
            break
        new_pts = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            ax, ay = a
            bx, by = b
            new_pts.append((0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by))
            new_pts.append((0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by))
        new_pts.append(pts[-1])
        pts = new_pts

    return pts


def _smooth_line(line, refinements=7, simplify_mm=0.060):
    if line is None or line.is_empty:
        return line

    if isinstance(line, LineString):
        if line.length < 0.25:
            return line
        coords = _chaikin_coords(list(line.coords), refinements=refinements)
        out = LineString(coords)
        # Simplify after smoothing to remove tiny pixel wiggles, but keep topology not required for lines.
        if simplify_mm > 0:
            out = out.simplify(simplify_mm, preserve_topology=False)
        return out

    if isinstance(line, MultiLineString):
        parts = [_smooth_line(g, refinements, simplify_mm) for g in line.geoms if not g.is_empty and g.length >= 0.25]
        return MultiLineString(parts) if parts else line

    if isinstance(line, GeometryCollection):
        parts = [_smooth_line(g, refinements, simplify_mm) for g in line.geoms if hasattr(g, "length") and g.length >= 0.25]
        return MultiLineString(parts) if parts else line

    return line



def _safe_text_filename(text: str, max_len: int = 72) -> str:
    """Human-readable, Windows/Telegram-safe filename stem; keeps Cyrillic."""
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip(" ._")
    if not value:
        value = "text"
    if len(value) > max_len:
        value = value[:max_len].rstrip(" ._")
    return value


def _resample_linestring(line: LineString, step_mm: float = 0.10):
    if line is None or line.is_empty or line.length <= step_mm:
        return line
    count = max(4, int(np.ceil(line.length / step_mm)) + 1)
    distances = np.linspace(0.0, line.length, count)
    pts = [line.interpolate(float(d)) for d in distances]
    return LineString([(p.x, p.y) for p in pts])



def _trim_line_ends(line: LineString, trim_mm: float = 0.055):
    """Trim tiny unstable end fragments which become hooks after stroke buffering."""
    if line is None or line.is_empty or line.length <= trim_mm * 2.5:
        return line
    start = float(trim_mm)
    end = float(line.length - trim_mm)
    count = max(4, int(np.ceil((end - start) / 0.075)) + 1)
    ds = np.linspace(start, end, count)
    pts = [line.interpolate(float(d)) for d in ds]
    return LineString([(p.x, p.y) for p in pts])


def _remove_tiny_centerline_parts(geom, min_length_mm: float = 0.32):
    """Remove only genuinely tiny skeleton fragments; preserve glyph structure."""
    if geom is None or geom.is_empty:
        return geom
    if isinstance(geom, LineString):
        return geom if geom.length >= min_length_mm else GeometryCollection()
    if isinstance(geom, MultiLineString):
        parts = [g for g in geom.geoms if (not g.is_empty and g.length >= min_length_mm)]
        return MultiLineString(parts) if parts else GeometryCollection()
    if isinstance(geom, GeometryCollection):
        parts = []
        for g in geom.geoms:
            if isinstance(g, LineString) and g.length >= min_length_mm:
                parts.append(g)
            elif isinstance(g, MultiLineString):
                parts.extend(x for x in g.geoms if x.length >= min_length_mm)
        return MultiLineString(parts) if parts else GeometryCollection()
    return geom


def _cubic_smooth_linestring(line: LineString, smoothing_mm: float = 0.026):
    """
    Smooth a centerline with a parametric cubic B-spline.
    This is isolated to TEXT stamps; image stamps keep the proven old pipeline.
    Falls back to Chaikin if SciPy rejects a short/degenerate segment.
    """
    if line is None or line.is_empty or line.length < 0.45:
        return line

    line = _resample_linestring(line, 0.085)
    coords = np.asarray(line.coords, dtype=float)
    if len(coords) < 4:
        return _smooth_line(line, refinements=5, simplify_mm=0.035)

    # Remove duplicate consecutive points.
    delta = np.linalg.norm(np.diff(coords, axis=0), axis=1)
    keep = np.r_[True, delta > 1e-6]
    coords = coords[keep]
    if len(coords) < 4:
        return _smooth_line(line, refinements=5, simplify_mm=0.035)

    try:
        from scipy.interpolate import splprep, splev
        # s is squared-distance budget. Scale by point count for stable behavior.
        s = max(1e-7, (float(smoothing_mm) ** 2) * len(coords))
        k = min(3, len(coords) - 1)
        tck, _ = splprep([coords[:, 0], coords[:, 1]], s=s, k=k)
        samples = max(16, int(np.ceil(line.length / 0.040)))
        u = np.linspace(0.0, 1.0, samples)
        x, y = splev(u, tck)
        out = LineString(np.column_stack([x, y]))
        out = out.simplify(0.002, preserve_topology=False)
        if not out.is_ring:
            out = _trim_line_ends(out, 0.045)
        return out
    except Exception:
        logger.exception("Cubic centerline smoothing fallback")
        return _smooth_line(line, refinements=6, simplify_mm=0.040)


def _smooth_text_centerlines(geom):
    if geom is None or geom.is_empty:
        return geom
    if isinstance(geom, LineString):
        return _cubic_smooth_linestring(geom)
    if isinstance(geom, MultiLineString):
        parts = [_cubic_smooth_linestring(g) for g in geom.geoms if not g.is_empty and g.length >= 0.35]
        return MultiLineString(parts) if parts else geom
    if isinstance(geom, GeometryCollection):
        parts = []
        for g in geom.geoms:
            if isinstance(g, LineString) and not g.is_empty and g.length >= 0.35:
                parts.append(_cubic_smooth_linestring(g))
            elif isinstance(g, MultiLineString):
                parts.extend(_cubic_smooth_linestring(x) for x in g.geoms if x.length >= 0.35)
        return MultiLineString(parts) if parts else geom
    return geom


def _build_text_relief_v130(mask, px_per_mm, target_w, target_h, line_width):
    """
    v1.6.2 text-only core:
      high-res text mask -> medial centerline -> fit -> cubic spline -> exact-width stroke.
    The old text pipeline remains available as a fallback.
    """
    line_geom = mask_to_centerline_line(mask, px_per_mm)
    if line_geom is None or line_geom.is_empty:
        raise RuntimeError("Не удалось построить centerline текста.")

    line_geom = _fit_line_geometry(line_geom, target_w, target_h, margin_mm=3.0)
    line_geom = _remove_tiny_centerline_parts(line_geom, min_length_mm=0.32)
    line_geom = _smooth_text_centerlines(line_geom)
    line_geom = _remove_tiny_centerline_parts(line_geom, min_length_mm=0.30)
    shape = _stroke_centerline(line_geom, line_width)
    if shape is None or shape.is_empty:
        raise RuntimeError("Не удалось построить векторный stroke текста.")
    return shape


def _stroke_clean_single_line(line_geom, line_width):
    """Exact stroke for clean single-line geometry; no legacy cleanup."""
    if line_geom is None or line_geom.is_empty:
        return None
    return line_geom.buffer(float(line_width)/2.0, cap_style=1, join_style=1, resolution=24)


def _stroke_centerline(line_geom, line_width):
    width = max(0.20, float(line_width))
    shape = line_geom.buffer(
        width / 2.0,
        cap_style=1,
        join_style=1,
        resolution=96,
    )
    shape = shape.buffer(0.006, resolution=96).buffer(-0.006, resolution=96).buffer(0)
    shape = shape.simplify(0.0025, preserve_topology=True).buffer(0)
    return shape


def _build_relief_from_mask(mask, px_per_mm, target_w, target_h, line_width):
    line_geom = mask_to_centerline_line(mask, px_per_mm)
    if line_geom is None or line_geom.is_empty:
        raise RuntimeError("Не удалось построить centerline линию.")

    # Correct order:
    # 1) fit unbuffered line
    # 2) smooth fitted line
    # 3) stroke exact width
    line_geom = _fit_line_geometry(line_geom, target_w, target_h, margin_mm=4.0)
    line_geom = _smooth_line(line_geom, refinements=7, simplify_mm=0.060)
    relief_shape = _stroke_centerline(line_geom, line_width)

    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Не удалось построить stroke для штампа.")
    return relief_shape



def _ttf_outline_to_exact_centerline_stroke(outline_shape, line_width, raster_px_per_mm=42):
    """
    STAMP ONLY — v1.6.2.

    The TTF engine gives us the real filled glyph outline.  A filled TTF outline
    cannot have an arbitrary 0.35 mm stroke width by definition, so for stamps
    we derive a medial centerline from that REAL TTF geometry, smooth it, and
    buffer the centerline to the requested physical width.

    Result:
      real TTF proportions -> centerline -> exact line_width mm stroke.

    Topper code is intentionally not involved.
    """
    if outline_shape is None or outline_shape.is_empty:
        raise RuntimeError("Пустая TTF-геометрия.")

    minx, miny, maxx, maxy = outline_shape.bounds
    pad_mm = 2.0
    ppm = int(max(28, min(60, raster_px_per_mm)))
    width_px = max(64, int(round((maxx - minx + 2 * pad_mm) * ppm)))
    height_px = max(64, int(round((maxy - miny + 2 * pad_mm) * ppm)))

    mask = Image.new("L", (width_px, height_px), 0)
    draw = ImageDraw.Draw(mask)

    def xy(x, y):
        px = (x - minx + pad_mm) * ppm
        py = (maxy - y + pad_mm) * ppm
        return (float(px), float(py))

    polys = []
    if outline_shape.geom_type == "Polygon":
        polys = [outline_shape]
    elif outline_shape.geom_type == "MultiPolygon":
        polys = list(outline_shape.geoms)
    elif hasattr(outline_shape, "geoms"):
        polys = [g for g in outline_shape.geoms if g.geom_type == "Polygon"]

    for poly in polys:
        draw.polygon([xy(x, y) for x, y in poly.exterior.coords], fill=255)
        for ring in poly.interiors:
            draw.polygon([xy(x, y) for x, y in ring.coords], fill=0)

    centerline = mask_to_centerline_line(mask, ppm)
    if centerline is None or centerline.is_empty:
        raise RuntimeError("Не удалось получить centerline из TTF.")

    # mask_to_centerline_line centers geometry on the raster canvas.
    # Re-center explicitly, then apply the stamp-only cleanup/smoothing.
    bx0, by0, bx1, by1 = centerline.bounds
    centerline = translate(
        centerline,
        xoff=-(bx0 + bx1) / 2.0,
        yoff=-(by0 + by1) / 2.0,
    )
    centerline = _remove_tiny_centerline_parts(centerline, min_length_mm=0.30)
    centerline = _smooth_text_centerlines(centerline)
    centerline = _remove_tiny_centerline_parts(centerline, min_length_mm=0.28)

    stroke = _stroke_clean_single_line(centerline, float(line_width))
    if stroke is None or stroke.is_empty:
        raise RuntimeError("Не удалось построить точный TTF stroke.")

    # Minimal topology repair only; do not inflate the requested width.
    stroke = stroke.buffer(0)
    return stroke



def build_stamp_from_text(
    text,
    output_dir,
    base_size="105",
    base_shape="round",
    line_width=0.45,
    font_choice="classic",
    add_heart=False,
    layout_mode="assembled",
):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    nominal, rw, rh, target_w, target_h = _fit_targets(base_size, base_shape)

    mask = render_text_mask(text, 82, PX_TEXT, font_choice)

    # v1.6.2 True Single-Line Text.
    # Supported Cyrillic is generated directly as pen trajectories:
    # no raster -> skeleton -> branch artifacts.
    active_font_path = None
    try:
        ttf_text = text_to_ttf_geometry(
            text,
            fonts_dir=Path(__file__).resolve().parent.parent / "fonts",
            font_choice=font_choice,
            target_width_mm=max(8.0, target_w - 6.0),
            target_height_mm=max(8.0, target_h - 6.0),
            line_spacing=0.90,
            curve_steps=22,
        )
        # v1.6.2: TTF outline defines the glyph STYLE, not the final physical
        # line thickness. Convert it to a smooth centerline and stroke that
        # centerline to the user's requested width (e.g. exactly 0.35 mm).
        relief_shape = _ttf_outline_to_exact_centerline_stroke(
            ttf_text.geometry,
            line_width=float(line_width),
            raster_px_per_mm=42,
        )
        geometry_core = "real_ttf_centerline_exact_width"
        active_font_path = ttf_text.font_path
    except Exception:
        logger.info("v1.6.2 single-line fallback to v1.3 core", exc_info=True)
        try:
            relief_shape = _build_text_relief_v130(mask, PX_TEXT, target_w, target_h, line_width)
            geometry_core = "text_v1_3_fallback"
        except Exception:
            logger.exception("v1.3 fallback failed; using v1.2 fallback")
            relief_shape = _build_relief_from_mask(mask, PX_TEXT, target_w, target_h, line_width)
            geometry_core = "text_v1_2_fallback"

    safe_name = _safe_text_filename(text)

    return _build_scene(
        relief_shape=relief_shape,
        output_dir=output,
        name=safe_name,
        base_size=base_size,
        base_shape=base_shape,
        line_width=line_width,
        add_heart=add_heart,
        layout_mode=layout_mode,
        preview_mask=mask,
        preview_shape=relief_shape if geometry_core in ("real_ttf_centerline_exact_width","real_ttf_vector_outline","true_single_line_cyrillic_exact_stroke") else None,
        meta_extra={
            "geometry_core": geometry_core,
            "stamp_text_mode": "real_ttf_style_centerline_exact_width",
            "single_line_font_style": font_choice,
            "ttf_font_path": active_font_path,
            "ttf_line_spacing": 0.90,
            "requested_stroke_width_mm": float(line_width),
            "stroke_width_mode": "exact_centerline_buffer",
            "px_per_mm": PX_TEXT,
        },
    )


def build_stamp_from_image(
    image_path,
    output_dir,
    base_size="105",
    base_shape="round",
    line_width=0.45,
    add_heart=False,
    layout_mode="assembled",
):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    mask = render_image_mask(image_path, 82, PX_IMAGE)
    nominal, rw, rh, target_w, target_h = _fit_targets(base_size, base_shape)
    relief_shape = _build_relief_from_mask(mask, PX_IMAGE, target_w, target_h, line_width)

    return _build_scene(
        relief_shape=relief_shape,
        output_dir=output,
        name=Path(image_path).stem or "image_stamp",
        base_size=base_size,
        base_shape=base_shape,
        line_width=line_width,
        add_heart=add_heart,
        layout_mode=layout_mode,
        preview_mask=mask,
        meta_extra={
            "geometry_core": "image_centerline_fit_strong_smooth_then_stroke",
            "source_image": str(image_path),
            "px_per_mm": PX_IMAGE,
        },
    )


def _preview_exact_geometry(path, name, relief_shape, base_shape, nominal, rw, rh, note=""):
    """Render the same final 2D relief geometry that is extruded into the 3MF."""
    from PIL import Image, ImageDraw
    W=1200; H=1200; pad=55
    img=Image.new("RGB",(W,H),(247,244,235)); d=ImageDraw.Draw(img)
    span=max(nominal if base_shape!="rect" else rw, nominal if base_shape!="rect" else rh)+8.0
    scale=(W-2*pad)/span
    def xy(x,y): return (W/2+x*scale,H/2-y*scale)
    if base_shape=="rect":
        x0,y0=xy(-rw/2,rh/2); x1,y1=xy(rw/2,-rh/2)
        d.rounded_rectangle((x0,y0,x1,y1),radius=18,fill=(232,195,121),outline=(135,91,38),width=4)
    else:
        x0,y0=xy(-nominal/2,nominal/2); x1,y1=xy(nominal/2,-nominal/2)
        d.ellipse((x0,y0,x1,y1),fill=(232,195,121),outline=(135,91,38),width=4)
    polys=[]
    if relief_shape.geom_type=="Polygon": polys=[relief_shape]
    elif relief_shape.geom_type=="MultiPolygon": polys=list(relief_shape.geoms)
    elif hasattr(relief_shape,"geoms"): polys=[g for g in relief_shape.geoms if g.geom_type=="Polygon"]
    for poly in polys:
        ext=[xy(x,y) for x,y in poly.exterior.coords]
        d.polygon(ext,fill=(25,92,58))
        for ring in poly.interiors:
            hole=[xy(x,y) for x,y in ring.coords]
            d.polygon(hole,fill=(232,195,121))
    d.text((25,20),f"CakeStampBot v1.6.2 STAMP — exact 3MF geometry",fill=(45,45,45))
    if note:d.text((25,H-35),note,fill=(70,70,70))
    img.save(path)


def _build_scene(
    relief_shape,
    output_dir,
    name,
    base_size,
    base_shape,
    line_width,
    add_heart,
    layout_mode,
    preview_mask,
    meta_extra=None,
    preview_shape=None,
):
    logger.info("STAMP BUILD START v1.6.2 | %s", name)

    nominal, rw, rh = parse_size(base_size, base_shape)

    relief = extrude_shape(relief_shape, RELIEF_H, "Relief")

    if base_shape == "rect":
        base = make_rect_base(rw, rh, BASE_H)
        base_name = f"Base_Rect_{int(rw)}x{int(rh)}mm"
    else:
        base = make_cylinder(nominal, BASE_H)
        base_name = f"Base_Round_{int(nominal)}mm"

    heart = heart_mesh(max(line_width, 0.35), RELIEF_H, -nominal * 0.30) if add_heart else None

    output = Path(output_dir)
    stls = []

    base_stl = str(output / f"{name}_{base_name}.stl")
    relief_stl = str(output / f"{name}_Relief.stl")
    base.export(base_stl)
    relief.export(relief_stl)
    stls += [base_stl, relief_stl]

    if heart is not None:
        heart_stl = str(output / f"{name}_Heart.stl")
        heart.export(heart_stl)
        stls.append(heart_stl)

    scene = trimesh.Scene()
    if layout_mode == "separate":
        # v1.6.2:
        # Objects are still separate in 3MF, but placed in the correct assembled position.
        # No more "letters flying away" in slicer.
        scene.add_geometry(base.copy(), geom_name=base_name, node_name=base_name)

        r = relief.copy()
        r.apply_translation([0, 0, BASE_H])
        scene.add_geometry(r, geom_name="Relief", node_name="Relief")

        if heart is not None:
            h = heart.copy()
            h.apply_translation([0, 0, BASE_H])
            scene.add_geometry(h, geom_name="Heart", node_name="Heart")

        suffix = "stamp_SEPARATE"
    else:
        scene.add_geometry(base.copy(), geom_name=base_name, node_name=base_name)

        r = relief.copy()
        r.apply_translation([0, 0, BASE_H])
        scene.add_geometry(r, geom_name="Relief", node_name="Relief")

        if heart is not None:
            h = heart.copy()
            h.apply_translation([0, 0, BASE_H])
            scene.add_geometry(h, geom_name="Heart", node_name="Heart")
        suffix = "stamp_ASSEMBLED"

    pp = str(output / f"{name}_preview.png")
    if preview_shape is not None and not preview_shape.is_empty:
        _preview_exact_geometry(pp, name, preview_shape, base_shape, nominal, rw, rh,
                                note=f"{meta_extra.get('single_line_font_style', 'classic').upper()} · exact stroke {line_width:.2f} mm")
    else:
        preview(pp, name, "stamp", preview_mask, note=f"Fallback centerline {line_width:.2f} mm")

    meta = {
        "version": "1.6.2",
        "mode": "stamp",
        "base_shape": base_shape,
        "base_size": base_size,
        "line_width": line_width,
        "base_height_mm": BASE_H,
        "relief_height_mm": RELIEF_H,
        "layout_mode": layout_mode,
        "objects": [base_name, "Relief"] + (["Heart"] if add_heart else []),
    }
    if meta_extra:
        meta.update(meta_extra)

    return export_bundle(output, name, scene, pp, stls, meta, suffix)
from .ttf_vector_engine import text_to_ttf_geometry
# STAMP-ONLY ENGINE: topper_engine must never import this module.
