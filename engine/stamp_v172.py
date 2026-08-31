"""CakeStampBot v1.8.6 physical text height fix.

The final text centerline is scaled to the requested physical text height
BEFORE the 0.25 mm stroke is created. This keeps text large while preserving
constant line width. Topper code is intentionally untouched.
"""
from __future__ import annotations

from shapely import affinity
from . import stamp_engine as _se


def _scale_centerline(line_geom, target_block_height_mm: float):
    if line_geom is None or line_geom.is_empty:
        return line_geom
    minx, miny, maxx, maxy = line_geom.bounds
    h = max(maxy - miny, 1e-9)
    factor = float(target_block_height_mm) / h
    scaled = affinity.scale(line_geom, xfact=factor, yfact=factor, origin=(0.0, 0.0))
    bx0, by0, bx1, by1 = scaled.bounds
    return affinity.translate(scaled, xoff=-(bx0 + bx1) / 2.0, yoff=-(by0 + by1) / 2.0)


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    size = max(10.0, min(16.0, float(text_size_mm)))
    exact_width = 0.25
    line_count = max(1, len(str(text).splitlines()))
    # text_size_mm means glyph/line height. Preserve useful inter-line spacing
    # instead of interpreting it as the height of the whole multiline block.
    target_block_h = size if line_count == 1 else size * (line_count + 0.20 * (line_count - 1))

    original_stroke = _se._stroke_clean_single_line
    original_scene = _se._build_scene

    def sized_exact_stroke(centerline, _line_width):
        centerline = _scale_centerline(centerline, target_block_h)
        # IMPORTANT: buffer only after physical-size scaling.
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
        meta["text_height_mode"] = "final_centerline_before_buffer"
        meta["stroke_width_mode"] = "exact_0.25mm_after_centerline_scale"
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
