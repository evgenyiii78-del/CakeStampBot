"""CakeStampBot v1.7.2 stamp-only compatibility wrapper.

Adds physical text height control and makes PNG preview use the exact final
relief geometry. Topper code is intentionally untouched.
"""
from __future__ import annotations

from . import stamp_engine as _se


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=7.0, add_heart=False, layout_mode="assembled"):
    size = max(5.0, min(10.0, float(text_size_mm)))
    original_ttf = _se.text_to_ttf_geometry
    original_scene = _se._build_scene

    def sized_ttf(*args, **kwargs):
        # Height is a physical millimetre target. Width remains constrained by
        # the stamp so long strings still fit safely inside the base.
        kwargs["target_height_mm"] = size
        return original_ttf(*args, **kwargs)

    def exact_preview_scene(*args, **kwargs):
        # The relief_shape here is exactly the 2D geometry later extruded into
        # the 3MF. Always render it for text stamps, including circular modes.
        if "relief_shape" in kwargs:
            kwargs["preview_shape"] = kwargs["relief_shape"]
        return original_scene(*args, **kwargs)

    _se.text_to_ttf_geometry = sized_ttf
    _se._build_scene = exact_preview_scene
    try:
        result = _se.build_stamp_from_text(
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
        return result
    finally:
        _se.text_to_ttf_geometry = original_ttf
        _se._build_scene = original_scene
