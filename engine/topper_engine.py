from pathlib import Path
import logging
import trimesh

from shapely.geometry import LineString, box
from shapely.ops import unary_union, nearest_points

from .common import *

logger = logging.getLogger("CakeStampEngine.Topper")

PX = 42
DEFAULT_LINE_WIDTH = 1.15

LEG_H = 45.0
LEG_W = 7.0


def _as_polys(shape):
    if shape is None or shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    return [g for g in getattr(shape, "geoms", []) if not g.is_empty and g.area > 0.01]


def _connect_components_minimal(shape, bridge_width=2.6):
    """
    Make all letters/lines physically connected with small rounded bridges.

    This is important for toppers:
    - text itself may have separate letters and even separate lines;
    - without bridges, a slicer can print loose parts;
    - we do not use a huge plaque, only small material links.
    """
    parts = _as_polys(shape)
    if not parts:
        return shape
    if len(parts) == 1:
        return parts[0].buffer(0)

    # Start from the largest part and connect the nearest remaining component.
    parts = sorted(parts, key=lambda g: g.area, reverse=True)
    connected = parts.pop(0)
    bridges = []

    while parts:
        best_i = 0
        best_d = None
        best_bridge = None

        for i, g in enumerate(parts):
            d = connected.distance(g)
            if best_d is None or d < best_d:
                p1, p2 = nearest_points(connected, g)
                bridge = LineString([(p1.x, p1.y), (p2.x, p2.y)]).buffer(
                    bridge_width / 2,
                    cap_style=1,
                    join_style=1,
                    resolution=64,
                )
                best_i = i
                best_d = d
                best_bridge = bridge

        connected = unary_union([connected, parts.pop(best_i), best_bridge]).buffer(0)
        bridges.append(best_bridge)

    return connected.buffer(0)


def _fit_pair(text_mesh, backing_mesh, max_w, max_h, y_shift=10):
    b = text_mesh.bounds
    w = b[1, 0] - b[0, 0]
    h = b[1, 1] - b[0, 1]
    s = min(max_w / w, max_h / h, 1.0)

    text_mesh.apply_scale([s, s, 1])
    backing_mesh.apply_scale([s, s, 1])

    b = text_mesh.bounds
    dx = -(b[0, 0] + b[1, 0]) / 2
    dy = -(b[0, 1] + b[1, 1]) / 2 + y_shift

    text_mesh.apply_translation([dx, dy, 0])
    backing_mesh.apply_translation([dx, dy, 0])
    return text_mesh, backing_mesh


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
    logger.info(
        "TOPPER BUILD START v0.8.4 | width=%s legs=%s text_h=%s backing_h=%s line_width=%s",
        width_mm,
        legs,
        text_height,
        backing_height,
        line_width,
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    mask = render_text_mask(text, 100, PX, font_choice)

    text_shape = mask_to_centerline_shape(mask, PX, line_width, 0.14)
    if text_shape is None or text_shape.is_empty:
        raise RuntimeError("Не удалось построить контур текста для топпера.")

    minx, miny, maxx, maxy = text_shape.bounds
    th = maxy - miny

    # Letter-shaped underlay: support under every stroke.
    underlay_pad = max(0.85, line_width * 0.62)
    letter_underlay = text_shape.buffer(
        underlay_pad,
        cap_style=1,
        join_style=1,
        resolution=64,
    ).buffer(0)

    # Minimal rounded bridges connect every separate letter/line.
    backing_shape = _connect_components_minimal(
        letter_underlay,
        bridge_width=max(2.4, line_width * 2.2),
    )

    # Bottom anchor rail for leg connection. This is narrow, not a plaque.
    rail_h = max(4.2, min(7.2, th * 0.20))
    rail_raw = box(minx - 4.0, miny - 1.2, maxx + 4.0, miny + rail_h)
    rail = rail_raw.buffer(1.6, resolution=64, cap_style=1, join_style=1).buffer(-1.6, resolution=64).buffer(0)
    backing_shape = unary_union([backing_shape, rail]).buffer(0)
    backing_shape = backing_shape.buffer(0.18, resolution=64).buffer(-0.18, resolution=64).buffer(0)

    text_mesh = extrude_shape(text_shape, text_height, "Topper_Text")
    backing_mesh = extrude_shape(backing_shape, backing_height, "Topper_Back_Letter_Bridge")

    _fit_pair(text_mesh, backing_mesh, width_mm * 0.92, width_mm * 0.38, y_shift=12)

    b = backing_mesh.bounds
    minx2, miny2, maxx2, maxy2 = b[0, 0], b[0, 1], b[1, 0], b[1, 1]
    backing_w = maxx2 - minx2

    # Auto legs: medium toppers get one leg, large toppers get two.
    if legs == "one":
        leg_count = 1
    elif legs == "two":
        leg_count = 2
    else:
        leg_count = 2 if width_mm >= 145 else 1

    if leg_count == 1:
        xs = [0.0]
    else:
        spread = min(width_mm * 0.34, max(42.0, backing_w * 0.34))
        xs = [-spread / 2, spread / 2]

    # Legs overlap the bottom rail so the topper is physically connected.
    leg_depth = LEG_H
    leg_y = miny2 - leg_depth / 2 + 2.5
    leg_z_height = max(backing_height, text_height * 0.80)

    legs_meshes = [
        make_rounded_box_mesh(
            f"Topper_Leg_{i + 1}",
            LEG_W,
            leg_depth,
            leg_z_height,
            x,
            leg_y,
            0,
            radius=min(LEG_W * 0.42, 3.0),
        )
        for i, x in enumerate(xs)
    ]

    # One-piece model:
    # text is lifted onto backing, but exported as ONE object.
    txt = text_mesh.copy()
    txt.apply_translation([0, 0, backing_height])

    onepiece = trimesh.util.concatenate([backing_mesh, txt] + legs_meshes)
    onepiece.metadata["name"] = "Topper_ONEPIECE"

    one_stl = str(output / "topper_ONEPIECE.stl")
    onepiece.export(one_stl)

    scene = trimesh.Scene()
    scene.add_geometry(onepiece, geom_name="Topper_ONEPIECE", node_name="Topper_ONEPIECE")

    preview_path = str(output / "topper_preview.png")
    preview(
        preview_path,
        "topper",
        "topper",
        mask,
        note=f"Topper text {text_height} mm, backing {backing_height} mm, legs {leg_count}, ONEPIECE",
    )

    meta = {
        "version": "0.8.4",
        "mode": "topper",
        "width_mm": width_mm,
        "text_height_mm": text_height,
        "backing_height_mm": backing_height,
        "line_width_mm": line_width,
        "legs": leg_count,
        "object": "Topper_ONEPIECE",
        "auto_legs_rule": "one leg below 145 mm, two legs from 145 mm",
        "note": "Topper is exported as one physical object: text + letter-shaped backing + bridges + leg(s).",
    }

    return export_bundle(output, "topper", scene, preview_path, [one_stl], meta, "topper_ONEPIECE")
