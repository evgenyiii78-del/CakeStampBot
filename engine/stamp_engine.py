
from pathlib import Path
import logging
import trimesh

from .common import *
from .vector_text import text_to_shape

logger = logging.getLogger("CakeStampEngine.StampV1_1_1")

PX = 36
RELIEF_H = 6.5
BASE_H = 0.7


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
    line_width=0.45,   # kept for bot compatibility, but no longer used for text stamps
    font_choice="classic",
    add_heart=False,
    layout_mode="assembled",
):
    """
    v1.1.1:
    Text stamp is now a SOLID vector relief (filled glyphs),
    not a hollow contour stroke.
    """
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

    # Full filled glyphs -> solid relief.
    relief_shape = vec.shape.buffer(0).simplify(0.010, preserve_topology=True).buffer(0)
    if relief_shape is None or relief_shape.is_empty:
        raise RuntimeError("Не удалось построить полнотелый векторный рельеф штампа.")

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
            "geometry_core": "vector_text_ttf_filled_glyphs",
            "font_path": vec.font_path,
            "actual_text_width_mm": vec.width_mm,
            "actual_text_height_mm": vec.height_mm,
            "stamp_text_mode": "solid_relief",
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
    """
    Image stamp remains in image centerline mode for now.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

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
    logger.info("STAMP BUILD START v1.1.1 | %s", name)

    nominal, rw, rh = parse_size(base_size, base_shape)

    relief = extrude_shape(relief_shape, RELIEF_H, "Relief")

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
    preview(pp, name, "stamp", preview_mask, note="Solid vector text stamp")

    meta = {
        "version": "1.1.1",
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
