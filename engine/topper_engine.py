
from pathlib import Path
import logging
import trimesh

from .common import *

logger = logging.getLogger("CakeStampEngine.Topper")

PX = 38

# Stable topper defaults.
DEFAULT_LINE_WIDTH = 1.20
LEG_H = 45.0
LEG_W = 8.0


def _fit_text(mesh, max_w, max_h, y_shift=0):
    b = mesh.bounds
    w = b[1, 0] - b[0, 0]
    h = b[1, 1] - b[0, 1]
    if w <= 0 or h <= 0:
        return mesh

    s = min(max_w / w, max_h / h, 1.0)
    mesh.apply_scale([s, s, 1])

    b = mesh.bounds
    dx = -(b[0, 0] + b[1, 0]) / 2
    dy = -(b[0, 1] + b[1, 1]) / 2 + y_shift
    mesh.apply_translation([dx, dy, 0])
    return mesh


def build_topper_from_text(
    text,
    output_dir,
    width_mm=120,
    font_choice="classic",
    text_height=3.0,
    backing_height=1.2,
    line_width=DEFAULT_LINE_WIDTH,
    legs="auto",
):
    """
    v0.8.5 stable topper geometry.

    Important design decision:
    We DO NOT boolean-union text and base into one mesh.
    We export a clean 3MF with two printable objects:
    - Topper_Base: rounded support strip + leg(s), watertight simple geometry.
    - Topper_Text: text relief, slightly overlaps/embeds into base.

    This avoids broken/non-manifold one-piece concatenation.
    In slicers the objects are placed together and print as one physical topper.
    """
    logger.info(
        "TOPPER BUILD START v0.8.5 | width=%s legs=%s text_h=%s backing_h=%s line=%s",
        width_mm, legs, text_height, backing_height, line_width
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # 1) Build text mesh.
    mask = render_text_mask(text, 100, PX, font_choice)
    text_shape = mask_to_centerline_shape(mask, PX, line_width, smooth=0.16)
    if text_shape is None or text_shape.is_empty:
        raise RuntimeError("Не удалось построить контур текста для топпера.")

    text_mesh = extrude_shape(text_shape, text_height, "Topper_Text")
    _fit_text(text_mesh, max_w=width_mm * 0.88, max_h=width_mm * 0.24, y_shift=9)

    tb = text_mesh.bounds
    minx, miny, maxx, maxy = tb[0,0], tb[0,1], tb[1,0], tb[1,1]
    text_w = maxx - minx
    text_h = maxy - miny

    # 2) Clean simple base, not a giant plaque.
    # A horizontal rounded support strip just behind/lower than the text.
    strip_w = min(width_mm * 0.96, max(text_w + 12.0, 70.0))
    strip_d = max(8.0, min(13.0, text_h * 0.42))
    strip_y = miny + strip_d * 0.35

    support_strip = make_rounded_box_mesh(
        "Topper_Support_Strip",
        strip_w,
        strip_d,
        backing_height,
        0.0,
        strip_y,
        0.0,
        radius=min(strip_d * 0.42, 3.2),
    )

    # 3) Legs connect into strip with overlap.
    if legs == "one":
        leg_count = 1
    elif legs == "two":
        leg_count = 2
    else:
        leg_count = 2 if width_mm >= 145 else 1

    if leg_count == 1:
        xs = [0.0]
    else:
        spread = min(width_mm * 0.34, max(42.0, strip_w * 0.34))
        xs = [-spread / 2, spread / 2]

    leg_depth = LEG_H
    leg_y = strip_y - strip_d / 2 - leg_depth / 2 + 2.8
    leg_z = max(backing_height, min(text_height, 2.8))

    leg_meshes = [
        make_rounded_box_mesh(
            f"Topper_Leg_{i+1}",
            LEG_W,
            leg_depth,
            leg_z,
            x,
            leg_y,
            0.0,
            radius=min(LEG_W * 0.42, 3.0),
        )
        for i, x in enumerate(xs)
    ]

    # Base can be concatenated because these are simple overlapped boxes,
    # and slicers handle this much more reliably than complex text unions.
    base_mesh = trimesh.util.concatenate([support_strip] + leg_meshes)
    base_mesh.metadata["name"] = "Topper_Base"

    # Text sits on top but sinks 0.20 mm into the base.
    text_on_base = text_mesh.copy()
    text_on_base.apply_translation([0, 0, max(0.0, backing_height - 0.20)])
    text_on_base.metadata["name"] = "Topper_Text"

    # Export separate STLs.
    base_stl = str(output / "topper_Base.stl")
    text_stl = str(output / "topper_Text.stl")
    base_mesh.export(base_stl)
    text_on_base.export(text_stl)

    # 3MF assembled with separate clean objects.
    scene = trimesh.Scene()
    scene.add_geometry(base_mesh, geom_name="Topper_Base", node_name="Topper_Base")
    scene.add_geometry(text_on_base, geom_name="Topper_Text", node_name="Topper_Text")

    preview_path = str(output / "topper_preview.png")
    preview(
        preview_path,
        "topper",
        "topper",
        mask,
        note=f"Topper v0.8.5, base strip, text {text_height} mm, backing {backing_height} mm, legs {leg_count}"
    )

    meta = {
        "version": "0.8.5",
        "mode": "topper",
        "width_mm": width_mm,
        "text_height_mm": text_height,
        "backing_height_mm": backing_height,
        "line_width_mm": line_width,
        "legs": leg_count,
        "objects": ["Topper_Base", "Topper_Text"],
        "auto_legs_rule": "one leg below 145 mm, two legs from 145 mm",
        "note": "Stable geometry: simple rounded base + separate embedded text, no forced bad one-piece mesh.",
    }

    return export_bundle(
        output,
        "topper",
        scene,
        preview_path,
        [base_stl, text_stl],
        meta,
        "topper_STABLE"
    )
