
from pathlib import Path
import logging
import trimesh

from shapely.geometry import LineString
from shapely.ops import unary_union

from .common import *
from .vector_text import text_to_shape

logger = logging.getLogger("CakeStampEngine.StampV1_1_0")

PX = 36
RELIEF_H = 6.5
BASE_H = 0.7


def _outline_stroke_from_filled_shape(filled_shape, line_width=0.45):
    """
    Convert filled glyph polygons to a clean outline stroke shape.
    This preserves smooth ovals and curves because the contours come from TTF,
    not from raster skeletonization.
    """
    geoms = []
    if filled_shape is None or filled_shape.is_empty:
        return None

    polys = [filled_shape] if filled_shape.geom_type == "Polygon" else list(getattr(filled_shape, "geoms", []))
    for poly in polys:
        if poly.is_empty or poly.area <= 0.01:
            continue
        rings = [poly.exterior] + list(poly.interiors)
        for ring in rings:
            line = LineString(list(ring.coords))
            if line.length < 0.25:
                continue
            geoms.append(
                line.buffer(
                    max(0.25, float(line_width)) / 2.0,
                    cap_style=1,
                    join_style=1,
                    resolution=48,
                )
            )

    if not geoms:
        return None

    merged = unary_union(geoms).buffer(0)
    # gentle cleanup; preserve smooth loops
    merged = merged.buffer(0.02, resolution=48).buffer(-0.02, resolution=48).buffer(0)
    merged = merged.simplify(0.008, preserve_topology=True).buffer(0)
    return merged


def _target_box(base_size, base_shape):
    nominal, rw, rh = parse_size(base_size, base_shape)
    if base_shape == "rect":
        return nominal, rw, rh, rw * 0.78, rh * 0.56
    return nominal, nominal, nominal, nominal * 0.72, nominal * 0.52


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

    nominal, rw, rh, target_w, target_h = _target_box(base_size, base_shape)

    vec = text_to_shape(
        text=text,
        font_choice=font_choice,
        target_width_mm=target_w,
        target_height_mm=target_h,
        line_spacing=0.92,
        curve_steps=20,
    )
    relief_shape = _outline_stroke_from_filled_shape(vec.shape, line_width=line_width)
    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Не удалось построить векторный контур штампа.")

    return _build_scene(
        relief_shape=relief_shape,
        output_dir=output,
        name="text_stamp",
        base_size=base_size,
        base_shape=base_shape,
        line_width=line_width,
        add_heart=add_heart,
        layout_mode=layout_mode,
        preview_mask=render_text_mask(text, 82, PX, font_choice),
        meta_extra={
            "geometry_core": "vector_text_ttf_outlines_to_outline_stroke",
            "font_path": vec.font_path,
            "actual_text_width_mm": vec.width_mm,
            "actual_text_height_mm": vec.height_mm,
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

    # Keep image mode on raster centerline for now.
    mask = render_image_mask(image_path, 82, PX)
    relief_shape = mask_to_centerline_shape(mask, PX, line_width=line_width)
    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Не удалось построить контур из картинки.")

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
            "geometry_core": "image_mask_centerline",
            "source_image": str(image_path),
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
    logger.info("STAMP BUILD START v1.1.0 | %s", name)

    nominal, rw, rh = parse_size(base_size, base_shape)

    relief = extrude_shape(relief_shape, RELIEF_H, "Relief")
    # final fit/centering safeguard
    if base_shape == "rect":
        center_and_fit(relief, rw * 0.78, rh * 0.56, 4)
        base = make_rect_base(rw, rh, BASE_H)
        base_name = f"Base_Rect_{int(rw)}x{int(rh)}mm"
    else:
        center_and_fit(relief, nominal * 0.72, nominal * 0.52, 4)
        base = make_cylinder(nominal, BASE_H)
        base_name = f"Base_Round_{int(nominal)}mm"

    heart = heart_mesh(max(line_width, 0.45), RELIEF_H, -nominal * 0.30) if add_heart else None

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
        b = base.copy()
        b.apply_translation([-nominal * 0.90, 0, 0])
        scene.add_geometry(b, geom_name=base_name, node_name=base_name)

        r = relief.copy()
        r.apply_translation([nominal * 0.25, 8, 0])
        scene.add_geometry(r, geom_name="Relief", node_name="Relief")

        if heart is not None:
            h = heart.copy()
            h.apply_translation([nominal * 0.85, 0, 0])
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
    preview(pp, name, "stamp", preview_mask, note=f"Vector stamp line {line_width:.2f} mm")

    meta = {
        "version": "1.1.0",
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
