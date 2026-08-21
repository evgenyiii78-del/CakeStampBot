
from pathlib import Path
import logging
import trimesh

from shapely.affinity import scale, translate
from shapely.geometry import LineString, MultiLineString, GeometryCollection

from .common import *

logger = logging.getLogger("CakeStampEngine.StampV1_2_2")

PX_TEXT = 72
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
    relief_shape = _build_relief_from_mask(mask, PX_TEXT, target_w, target_h, line_width)

    return _build_scene(
        relief_shape=relief_shape,
        output_dir=output,
        name="text_stamp",
        base_size=base_size,
        base_shape=base_shape,
        line_width=line_width,
        add_heart=add_heart,
        layout_mode=layout_mode,
        preview_mask=mask,
        meta_extra={
            "geometry_core": "text_centerline_fit_strong_smooth_then_stroke",
            "stamp_text_mode": "centerline_fit_strong_smooth_then_stroke",
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
):
    logger.info("STAMP BUILD START v1.2.7 | %s", name)

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
        # v1.2.7:
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
    preview(pp, name, "stamp", preview_mask, note=f"Fit→StrongSmooth→Stroke layout-fixed {line_width:.2f} mm")

    meta = {
        "version": "1.2.3",
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
