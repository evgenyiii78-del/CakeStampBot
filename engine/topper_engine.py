
from pathlib import Path
import logging
import trimesh

from shapely.geometry import LineString, box
from shapely.ops import unary_union, nearest_points

from .common import *
from .vector_text import text_to_shape

logger = logging.getLogger("CakeStampEngine.TopperV1_0_2")

DEFAULT_TEXT_HEIGHT = 2.8
DEFAULT_BACKING_HEIGHT = 1.3
DEFAULT_BACKING_MARGIN = 1.18

LEG_LEN = 45.0
LEG_W = 3.0


def _as_polys(shape):
    if shape is None or shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    return [g for g in getattr(shape, "geoms", []) if not g.is_empty and g.area > 0.01]


def _connect_components(shape, bridge_width=2.0):
    """
    Minimal nearest-neighbour bridges so all islands become one printable text base.
    """
    parts = [p for p in _as_polys(shape) if p.area >= 0.16]
    if not parts:
        return shape
    if len(parts) == 1:
        return parts[0].buffer(0)

    parts = [p.simplify(0.016, preserve_topology=True).buffer(0) for p in parts]
    parts = sorted(parts, key=lambda g: g.area, reverse=True)
    connected = parts.pop(0)
    links = 0
    max_links = 80

    while parts and links < max_links:
        best_i = 0
        best_d = None
        best_bridge = None
        for i, g in enumerate(parts):
            d = connected.distance(g)
            if best_d is None or d < best_d:
                p1, p2 = nearest_points(connected, g)
                best_bridge = LineString([(p1.x, p1.y), (p2.x, p2.y)]).buffer(
                    bridge_width / 2.0, cap_style=1, join_style=1, resolution=24
                )
                best_i = i
                best_d = d
        connected = unary_union([connected, parts.pop(best_i), best_bridge]).buffer(0)
        links += 1

    if parts:
        connected = unary_union([connected] + parts).buffer(0)

    return connected.buffer(0).simplify(0.008, preserve_topology=True).buffer(0)


def _force_two_line_bridges(base_shape, bridge_width=3.0):
    """
    v1.5.0:
    Create two deliberate vertical bridge pads between two text lines.

    The old method sometimes found tiny accidental nearest links.
    This method detects upper/lower clusters and places two rounded bridge
    columns in the overlap/span zone.
    """
    parts = [p for p in _as_polys(base_shape) if p.area >= 0.16]
    if len(parts) < 2:
        return base_shape

    ys = [p.centroid.y for p in parts]
    y_mid = (min(ys) + max(ys)) / 2.0

    top = [p for p in parts if p.centroid.y >= y_mid]
    bottom = [p for p in parts if p.centroid.y < y_mid]

    if not top or not bottom:
        return base_shape

    top_union = unary_union(top).buffer(0)
    bot_union = unary_union(bottom).buffer(0)

    tminx, tminy, tmaxx, tmaxy = top_union.bounds
    bminx, bminy, bmaxx, bmaxy = bot_union.bounds

    # Use horizontal overlap when possible; otherwise use shared total span.
    overlap_min = max(tminx, bminx)
    overlap_max = min(tmaxx, bmaxx)

    if overlap_max - overlap_min < 12.0:
        overlap_min = max(min(tminx, bminx), min(tmaxx, bmaxx) - 55.0)
        overlap_max = min(max(tmaxx, bmaxx), max(tminx, bminx) + 55.0)

    span = max(overlap_max - overlap_min, 1.0)

    # Two bridges, not one. Place them away from the exact center.
    xs = [
        overlap_min + span * 0.34,
        overlap_min + span * 0.66,
    ]

    gap_y0 = bmaxy - 0.8
    gap_y1 = tminy + 0.8

    if gap_y1 < gap_y0:
        gap_y0, gap_y1 = gap_y1, gap_y0

    bridge_height = max(gap_y1 - gap_y0, 2.0)

    bridges = []
    for x in xs:
        # Rounded vertical pad.
        raw = box(
            x - bridge_width / 2.0,
            gap_y0,
            x + bridge_width / 2.0,
            gap_y1,
        )

        bridge = raw.buffer(
            bridge_width * 0.35,
            resolution=32,
            join_style=1,
        ).buffer(
            -bridge_width * 0.35,
            resolution=32,
        ).buffer(0)

        # If the gap is tiny, still add a circular-ish weld pad.
        if bridge.is_empty or bridge.area < 0.3:
            bridge = box(
                x - bridge_width / 2.0,
                gap_y0 - 0.8,
                x + bridge_width / 2.0,
                gap_y1 + 0.8,
            ).buffer(0.6, resolution=32).buffer(0)

        bridges.append(bridge)

    return unary_union([base_shape] + bridges).buffer(0)


def _make_beveled_leg_mesh(name, width=3.0, length=45.0, height=2.8):
    """
    Separate topper leg with a one-sided bevel at the insertion end.
    XY shape is mostly 3 mm wide, but the bottom tip has a diagonal cut
    so it is easier to insert into cake.
    """
    from shapely.geometry import Polygon

    w = float(width)
    L = float(length)
    bevel = min(8.0, L * 0.22)

    # Coordinates: top near y=+L/2, insertion end at y=-L/2.
    # One side is cut diagonally: easier to pierce, still printable flat.
    pts = [
        (-w / 2.0,  L / 2.0),
        ( w / 2.0,  L / 2.0),
        ( w / 2.0, -L / 2.0 + bevel),
        (-w / 2.0, -L / 2.0),
    ]

    shape = Polygon(pts).buffer(0)

    # Tiny fillet to avoid razor-stress corners, without making it fat.
    shape = shape.buffer(0.08, resolution=16, join_style=1).buffer(-0.08, resolution=16).buffer(0)

    mesh = extrude_shape(shape, height, name)
    mesh.metadata["name"] = name
    return mesh


def _make_leg_meshes(width_mm: float, legs: str, backing_bounds, backing_height: float, text_height: float):
    """
    v1.5.0:
    Always create 2 separate beveled legs.
    The user can delete one in the slicer if needed.
    """
    minx, miny, maxx, maxy = backing_bounds
    count = 2

    # Put legs at about 38% of text/base width, but keep sane limits.
    textbase_w = maxx - minx
    spread = min(width_mm * 0.42, max(34.0, textbase_w * 0.38))
    xs = [-spread / 2.0, spread / 2.0]

    leg_meshes = []
    for i, x in enumerate(xs):
        leg_mesh = _make_beveled_leg_mesh(
            f"Topper_Leg_{i+1}",
            width=LEG_W,
            length=LEG_LEN,
            height=max(backing_height, min(2.8, text_height)),
        )
        # Keep legs separate. X offset is applied here; caller places them aside in 3MF.
        leg_mesh.apply_translation([x, 0, 0])
        leg_meshes.append(leg_mesh)

    return leg_meshes, count


def build_topper_from_text(
    text,
    output_dir,
    width_mm=120,
    font_choice="classic",
    text_height=DEFAULT_TEXT_HEIGHT,
    backing_height=DEFAULT_BACKING_HEIGHT,
    line_width=1.20,  # kept for bot compatibility
    legs="auto",
):
    """
    v1.5.0:
    - TextBase is one unified object: text-shaped backing + bridges.
    - Leg(s) are separate objects in 3MF so user can position them in slicer.
    - Reduced line spacing.
    - Two explicit bridges between lines for 2-line text.
    """
    logger.info(
        "TOPPER BUILD START v1.5.0 | width=%s font=%s text_h=%s backing_h=%s legs=%s",
        width_mm, font_choice, text_height, backing_height, legs
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    vec = text_to_shape(
        text=text,
        font_choice=font_choice,
        target_width_mm=width_mm * 0.88,
        target_height_mm=width_mm * 0.34,
        line_spacing=0.82,
        curve_steps=20,
    )
    text_shape = vec.shape.buffer(0).simplify(0.012, preserve_topology=True).buffer(0)
    if text_shape.length > 2500:
        text_shape = text_shape.simplify(0.035, preserve_topology=True).buffer(0)

    # Backing follows letters and is slightly wider.
    backing_shape = text_shape.buffer(
        DEFAULT_BACKING_MARGIN,
        cap_style=1,
        join_style=1,
        resolution=32,
    ).buffer(0)

    # Auto connect all islands.
    backing_shape = _connect_components(backing_shape, bridge_width=2.0)
    # Explicitly bridge two lines in two places.
    backing_shape = _force_two_line_bridges(backing_shape, bridge_width=3.0)
    # Final cleanup.
    backing_shape = backing_shape.buffer(0.03, resolution=32).buffer(-0.03, resolution=32).buffer(0)

    base_mesh = extrude_shape(backing_shape, backing_height, "Topper_TextBase")
    base_mesh.metadata["name"] = "Topper_TextBase"

    text_mesh = extrude_shape(text_shape, text_height, "Topper_Text")
    text_mesh.apply_translation([0, 0, max(0.0, backing_height - 0.20)])
    text_mesh.metadata["name"] = "Topper_Text"

    # Separate leg objects, not assembled.
    leg_meshes, leg_count = _make_leg_meshes(
        width_mm=width_mm,
        legs=legs,
        backing_bounds=backing_shape.bounds,
        backing_height=backing_height,
        text_height=text_height,
    )

    # Export STLs.
    exported_stls = []
    base_stl = str(output / "topper_TextBase.stl")
    text_stl = str(output / "topper_Text.stl")
    base_mesh.export(base_stl)
    text_mesh.export(text_stl)
    exported_stls.extend([base_stl, text_stl])

    scene = trimesh.Scene()
    scene.add_geometry(base_mesh, geom_name="Topper_TextBase", node_name="Topper_TextBase")
    scene.add_geometry(text_mesh, geom_name="Topper_Text", node_name="Topper_Text")

    for i, leg_mesh in enumerate(leg_meshes, start=1):
        # Put separate beveled leg(s) aside in XY so preview in slicer shows them detached.
        shifted = leg_mesh.copy()
        # place to the left of the textbase by default
        minx, miny, maxx, maxy = backing_shape.bounds
        xoff = minx - 12.0 - (i - 1) * 6.0
        shifted.apply_translation([xoff, 0, 0])
        leg_stl = str(output / f"topper_Leg_{i}.stl")
        shifted.export(leg_stl)
        exported_stls.append(leg_stl)
        scene.add_geometry(shifted, geom_name=f"Topper_Leg_{i}", node_name=f"Topper_Leg_{i}")

    # Preview for telegram only.
    mask = render_text_mask(text, 100, 32, font_choice)
    preview_path = str(output / "topper_preview.png")
    preview(
        preview_path,
        "topper",
        "topper",
        mask,
        note=f"Topper v1.5.0, TextBase + 2 separate beveled legs, spacing 0.82"
    )

    meta = {
        "version": "1.0.3",
        "mode": "topper",
        "geometry_core": "vector_text_ttf_outlines",
        "font_path": vec.font_path,
        "width_mm": width_mm,
        "actual_text_width_mm": vec.width_mm,
        "actual_text_height_mm": vec.height_mm,
        "text_height_mm": text_height,
        "backing_height_mm": backing_height,
        "backing_margin_mm": DEFAULT_BACKING_MARGIN,
        "line_spacing": 0.82,
        "leg_width_mm": LEG_W,
        "leg_length_mm": LEG_LEN,
        "legs": 2,
        "objects": ["Topper_TextBase", "Topper_Text"] + [f"Topper_Leg_{i}" for i in range(1, leg_count+1)],
        "note": "v1.5.0: unified textbase, separate beveled leg objects, two stronger explicit bridge pads between lines, tighter spacing.",
    }

    return export_bundle(
        output,
        "topper",
        scene,
        preview_path,
        exported_stls,
        meta,
        "topper_TEXTBASE_SEPARATE_LEGS"
    )
