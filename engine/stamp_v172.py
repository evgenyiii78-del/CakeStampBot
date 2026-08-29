"""CakeStampBot v1.8.3 stamp text sizing.

Physical text height is enforced on final stamp geometry. Supported UI range
is 10-16 mm. Circular radius remains controlled by stamp_engine; topper code
is intentionally untouched.
"""
from __future__ import annotations

from shapely import affinity
from . import stamp_engine as _se


def _force_final_height(shape, target_mm: float):
    if shape is None or shape.is_empty:
        return shape
    minx, miny, maxx, maxy = shape.bounds
    h = max(maxy - miny, 1e-9)
    factor = float(target_mm) / h
    return affinity.scale(shape, xfact=factor, yfact=factor, origin=(0.0, 0.0))


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    size = max(10.0, min(16.0, float(text_size_mm)))
    original_ttf = _se.text_to_ttf_geometry
    original_warp = _se._warp_shape_to_circle
    original_scene = _se._build_scene

    def sized_ttf(*args, **kwargs):
        kwargs["target_height_mm"] = size
        return original_ttf(*args, **kwargs)

    def sized_warp(shape, base_diameter_mm, mode):
        return original_warp(_force_final_height(shape, size), base_diameter_mm, mode)

    def exact_preview_scene(*args, **kwargs):
        meta = kwargs.get("meta_extra") or {}
        path = str(meta.get("text_path", text_path or "normal")).lower()
        relief = kwargs.get("relief_shape")
        if relief is not None and path == "normal":
            relief = _force_final_height(relief, size)
            kwargs["relief_shape"] = relief
        if relief is not None:
            kwargs["preview_shape"] = relief
        meta["requested_text_height_mm"] = size
        meta["text_height_mode"] = "exact_final_geometry"
        kwargs["meta_extra"] = meta
        return original_scene(*args, **kwargs)

    _se.text_to_ttf_geometry = sized_ttf
    _se._warp_shape_to_circle = sized_warp
    _se._build_scene = exact_preview_scene
    try:
        return _se.build_stamp_from_text(
            text=text,
            output_dir=output_dir,
            base_size=base_size,
            base_shape=base_shape,
            line_width=line_width,
            font_choice=font_choice,
            text_path=text_path,
            add_heart=add_heart,
            layout_mode=layout_mode,
        )
    finally:
        _se.text_to_ttf_geometry = original_ttf
        _se._warp_shape_to_circle = original_warp
        _se._build_scene = original_scene
