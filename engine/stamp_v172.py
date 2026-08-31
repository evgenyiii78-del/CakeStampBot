"""CakeStampBot v1.8.7 text layout fix.

Text keeps an approximately 20 mm safe margin from the stamp edge and uses
tighter multiline spacing. The centerline is fitted BEFORE the exact 0.25 mm
stroke, so fitting never changes line width. Topper is intentionally untouched.
"""
from __future__ import annotations

from shapely import affinity
from . import stamp_engine as _se

SAFE_MARGIN_MM = 20.0
LINE_GAP_FACTOR = 0.08


def _scale_centerline(line_geom, target_block_height_mm: float, max_width_mm: float, max_height_mm: float):
    if line_geom is None or line_geom.is_empty:
        return line_geom
    minx, miny, maxx, maxy = line_geom.bounds
    w = max(maxx - minx, 1e-9)
    h = max(maxy - miny, 1e-9)

    # First honor the requested physical text/block height, then constrain the
    # complete text block to the 20 mm safe area. Uniform scaling preserves
    # glyph proportions. The 0.25 mm buffer is applied afterwards.
    requested_scale = float(target_block_height_mm) / h
    fit_w = float(max_width_mm) / w
    fit_h = float(max_height_mm) / h
    factor = min(requested_scale, fit_w, fit_h)

    scaled = affinity.scale(line_geom, xfact=factor, yfact=factor, origin=(0.0, 0.0))
    bx0, by0, bx1, by1 = scaled.bounds
    return affinity.translate(scaled, xoff=-(bx0 + bx1) / 2.0, yoff=-(by0 + by1) / 2.0)


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    size = max(10.0, min(16.0, float(text_size_mm)))
    exact_width = 0.25
    line_count = max(1, len(str(text).splitlines()))

    # Tighter line spacing: only ~8% extra between lines.
    target_block_h = size if line_count == 1 else size * (line_count + LINE_GAP_FACTOR * (line_count - 1))

    nominal, rw, rh = _se.parse_size(base_size, base_shape)
    if base_shape == "rect":
        safe_w = max(10.0, float(rw) - 2.0 * SAFE_MARGIN_MM)
        safe_h = max(10.0, float(rh) - 2.0 * SAFE_MARGIN_MM)
    else:
        safe_w = max(10.0, float(nominal) - 2.0 * SAFE_MARGIN_MM)
        safe_h = safe_w

    original_stroke = _se._stroke_clean_single_line
    original_scene = _se._build_scene

    def sized_exact_stroke(centerline, _line_width):
        centerline = _scale_centerline(centerline, target_block_h, safe_w, safe_h)
        return original_stroke(centerline, exact_width)

    def exact_preview_scene(*args, **kwargs):
        relief = kwargs.get("relief_shape")
        if relief is not None:
            kwargs["preview_shape"] = relief
        meta = kwargs.get("meta_extra") or {}
        meta["requested_text_height_mm"] = size
        meta["requested_stroke_width_mm"] = exact_width
        meta["text_line_count"] = line_count
        meta["target_text_block_height_mm"] = target_block_h
        meta["safe_margin_mm"] = SAFE_MARGIN_MM
        meta["safe_text_width_mm"] = safe_w
        meta["safe_text_height_mm"] = safe_h
        meta["line_gap_factor"] = LINE_GAP_FACTOR
        meta["text_height_mode"] = "centerline_height_then_safe_area_fit"
        meta["stroke_width_mode"] = "exact_0.25mm_after_all_scaling"
        kwargs["meta_extra"] = meta
        return original_scene(*args, **kwargs)

    _se._stroke_clean_single_line = sized_exact_stroke
    _se._build_scene = exact_preview_scene
    try:
        return _se.build_stamp_from_text(
            text=text,
            output_dir=output_dir,
            base_size=base_size,
            base_shape=base_shape,
            line_width=exact_width,
            font_choice=font_choice,
            text_path=text_path,
            add_heart=add_heart,
            layout_mode=layout_mode,
        )
    finally:
        _se._stroke_clean_single_line = original_stroke
        _se._build_scene = original_scene
