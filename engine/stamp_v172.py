"""CakeStampBot v1.8.4 stamp text sizing + exact line width.

Text height is applied to the TTF outline BEFORE stamp_engine derives the
centerline and buffers it. Therefore changing text height no longer scales the
already-buffered 0.25 mm stroke. Topper code is intentionally untouched.
"""
from __future__ import annotations

from shapely import affinity
from . import stamp_engine as _se


def _scale_outline_to_height(shape, target_mm: float):
    """Uniformly scale an unbuffered TTF outline to the requested height."""
    if shape is None or shape.is_empty:
        return shape
    minx, miny, maxx, maxy = shape.bounds
    height = max(maxy - miny, 1e-9)
    factor = float(target_mm) / height
    return affinity.scale(shape, xfact=factor, yfact=factor, origin=(0.0, 0.0))


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    size = max(10.0, min(16.0, float(text_size_mm)))
    exact_width = 0.25

    original_ttf = _se.text_to_ttf_geometry
    original_scene = _se._build_scene

    def sized_ttf(*args, **kwargs):
        # Let the real TTF engine build the glyphs, then resize the UNBUFFERED
        # outline. stamp_engine subsequently extracts its centerline and applies
        # the final exact-width stroke, so 10..16 mm never changes 0.25 mm.
        result = original_ttf(*args, **kwargs)
        result.geometry = _scale_outline_to_height(result.geometry, size)
        return result

    def exact_preview_scene(*args, **kwargs):
        relief = kwargs.get("relief_shape")
        if relief is not None:
            kwargs["preview_shape"] = relief
        meta = kwargs.get("meta_extra") or {}
        meta["requested_text_height_mm"] = size
        meta["requested_stroke_width_mm"] = exact_width
        meta["text_height_mode"] = "pre_centerline_ttf_outline_scale"
        meta["stroke_width_mode"] = "exact_centerline_buffer_after_text_scale"
        kwargs["meta_extra"] = meta
        return original_scene(*args, **kwargs)

    _se.text_to_ttf_geometry = sized_ttf
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
        _se.text_to_ttf_geometry = original_ttf
        _se._build_scene = original_scene
