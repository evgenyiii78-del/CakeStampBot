
from pathlib import Path
import logging

from shapely.geometry import LineString, box
from shapely.ops import unary_union, nearest_points

from .common import *
from .vector_text import text_to_shape

logger = logging.getLogger("CakeStampEngine.TopperV1")

# v1.0 real vector topper engine.
DEFAULT_TEXT_HEIGHT = 3.0
DEFAULT_BACKING_HEIGHT = 1.3
DEFAULT_BACKING_MARGIN = 1.05

LEG_LEN = 45.0
LEG_W = 3.0


def _as_polys(shape):
    if shape is None or shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    return [g for g in getattr(shape, "geoms", []) if not g.is_empty and g.area > 0.01]


def _connect_components(shape, bridge_width=2.0):
    parts = _as_polys(shape)
    # Drop tiny dust; dots/important accents are normally above this.
    parts = [p for p in parts if p.area >= 0.18]
    if not parts:
        return shape
    if len(parts) == 1:
        return parts[0].buffer(0)

    # Too many islands can make nearest_points O(n²) slow.
    # Keep all meaningful parts, but simplify slightly first.
    parts = [p.simplify(0.018, preserve_topology=True).buffer(0) for p in parts]
    parts = sorted(parts, key=lambda g: g.area, reverse=True)

    connected = parts.pop(0)
    max_links = 80
    links = 0

    while parts and links < max_links:
        best_i = 0
        best_d = None
        best_bridge = None

        for i, g in enumerate(parts):
            d = connected.distance(g)
            if best_d is None or d < best_d:
                p1, p2 = nearest_points(connected, g)
                best_bridge = LineString([(p1.x, p1.y), (p2.x, p2.y)]).buffer(
                    bridge_width / 2.0,
                    cap_style=1,
                    join_style=1,
                    resolution=24,
                )
                best_i = i
                best_d = d

        connected = unary_union([connected, parts.pop(best_i), best_bridge]).buffer(0)
        links += 1

    if parts:
        connected = unary_union([connected] + parts).buffer(0)

    return connected.buffer(0).simplify(0.012, preserve_topology=True).buffer(0)


def _leg_shapes(backing_shape, width_mm: float, legs: str):
    minx, miny, maxx, maxy = backing_shape.bounds

    if legs == "two":
        count = 2
    elif legs == "one":
        count = 1
    else:
        count = 2 if width_mm >= 150 else 1

    if count == 1:
        xs = [0.0]
    else:
        spread = min(width_mm * 0.34, max(42.0, (maxx - minx) * 0.32))
        xs = [-spread / 2.0, spread / 2.0]

    shapes = []
    for x in xs:
        # 3 mm square-width stake. It overlaps the letter backing by 1.4 mm.
        raw = box(
            x - LEG_W / 2.0,
            miny - LEG_LEN + 1.4,
            x + LEG_W / 2.0,
            miny + 1.4,
        )
        # tiny fillet only to remove slicer-stress corners; final width stays ~3 mm.
        leg = raw.buffer(0.20, resolution=32, join_style=1).buffer(-0.20, resolution=32).buffer(0)
        shapes.append(leg)

    return shapes, count


def build_topper_from_text(
    text,
    output_dir,
    width_mm=120,
    font_choice="classic",
    text_height=DEFAULT_TEXT_HEIGHT,
    backing_height=DEFAULT_BACKING_HEIGHT,
    line_width=1.20,  # kept for bot compatibility; vector topper uses real glyph outlines
    legs="auto",
):
    """
    v1.0 Core Rewrite for topper:
    - TTF glyph outlines -> vector polygons;
    - letter-shaped backing slightly wider than letters;
    - minimal bridges connect separate letters/lines;
    - 3 mm stake leg(s), not T-shaped;
    - base is one clean 2D union extruded once;
    - text is a clean vector object slightly embedded into base.
    """
    logger.info(
        "TOPPER BUILD START v1.0.1 | width=%s font=%s text_h=%s backing_h=%s legs=%s",
        width_mm, font_choice, text_height, backing_height, legs
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    vec = text_to_shape(
        text=text,
        font_choice=font_choice,
        target_width_mm=width_mm * 0.88,
        target_height_mm=width_mm * 0.34,
        line_spacing=1.15,
        curve_steps=20,
    )
    text_shape = vec.shape.buffer(0).simplify(0.018, preserve_topology=True).buffer(0)
    # v1.0.1: guard against pathological geometry on small hosting CPUs.
    if text_shape.length > 2500:
        text_shape = text_shape.simplify(0.035, preserve_topology=True).buffer(0)

    # Letter backing follows the actual vector letters and is slightly wider.
    backing_shape = text_shape.buffer(
        DEFAULT_BACKING_MARGIN,
        cap_style=1,
        join_style=1,
        resolution=32,
    ).buffer(0)

    # Connect all separate islands with small rounded bridges.
    backing_shape = _connect_components(backing_shape, bridge_width=2.0)

    # Add one or two 3 mm legs into the 2D backing union.
    legs_polys, leg_count = _leg_shapes(backing_shape, width_mm, legs)
    base_shape = unary_union([backing_shape] + legs_polys).buffer(0)

    # Gentle cleanup; no aggressive simplification.
    base_shape = base_shape.buffer(0.02, resolution=32).buffer(-0.04, resolution=32).buffer(0)

    base_mesh = extrude_shape(base_shape, backing_height, "Topper_Base")
    text_mesh = extrude_shape(text_shape, text_height, "Topper_Text")

    # Text is embedded 0.20 mm into the base so slicer prints it as fused material.
    text_mesh.apply_translation([0, 0, max(0.0, backing_height - 0.20)])

    # Export separate clean objects.
    base_stl = str(output / "topper_Base.stl")
    text_stl = str(output / "topper_Text.stl")
    base_mesh.export(base_stl)
    text_mesh.export(text_stl)

    scene = trimesh.Scene()
    scene.add_geometry(base_mesh, geom_name="Topper_Base", node_name="Topper_Base")
    scene.add_geometry(text_mesh, geom_name="Topper_Text", node_name="Topper_Text")

    # Preview still uses raster image for Telegram only; model geometry is vector.
    mask = render_text_mask(text, 100, 32, font_choice)
    preview_path = str(output / "topper_preview.png")
    preview(
        preview_path,
        "topper",
        "topper",
        mask,
        note=f"Topper v1.0, vector text, backing + {leg_count} leg(s) 3 mm"
    )

    meta = {
        "version": "1.0.1",
        "mode": "topper",
        "geometry_core": "vector_text_ttf_outlines",
        "font_path": vec.font_path,
        "width_mm": width_mm,
        "actual_text_width_mm": vec.width_mm,
        "actual_text_height_mm": vec.height_mm,
        "text_height_mm": text_height,
        "backing_height_mm": backing_height,
        "backing_margin_mm": DEFAULT_BACKING_MARGIN,
        "leg_width_mm": LEG_W,
        "leg_length_mm": LEG_LEN,
        "legs": leg_count,
        "objects": ["Topper_Base", "Topper_Text"],
        "note": "v1.0 vector core: no raster skeleton for topper text; clean letter-shaped backing + 3mm leg(s).",
    }

    return export_bundle(
        output,
        "topper",
        scene,
        preview_path,
        [base_stl, text_stl],
        meta,
        "topper_V1_VECTOR"
    )
