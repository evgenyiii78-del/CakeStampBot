import logging
import os

from .stamp_v172 import build_stamp_from_text as _build_stamp_from_text_legacy
from .stamp_engine import build_stamp_from_image
from .topper_engine import build_topper_from_text
from . import blender_text_engine as _blender_text_engine
from .stamp_fix_v235 import apply_fixes as _apply_stamp_v235_fixes
from .stamp_font_fix_v242 import apply_fixes as _apply_stamp_font_v242_fixes

# v2.4.0 geometry/crown fixes first, then v2.4.2 thin true-TTF contour handling.
# Topper remains on its existing engine.
_apply_stamp_v235_fixes(_blender_text_engine)
_apply_stamp_font_v242_fixes(_blender_text_engine)
build_stamp_from_text_blender = _blender_text_engine.build_stamp_from_text_blender
blender_available = _blender_text_engine.blender_available

logger = logging.getLogger("CakeStampEngine.Dispatch")


def build_stamp_from_text(**kwargs):
    """Dispatch text stamps to Blender, with a compatibility-safe legacy fallback."""
    mode = os.getenv("STAMP_TEXT_ENGINE", "auto").strip().lower()
    wants_blender = mode in {"auto", "blender", "blender_strict"}
    blender_error = None

    if wants_blender and blender_available():
        try:
            logger.info(
                "TEXT STAMP ENGINE: Blender | path=%s crown=%s font=%s width=%s",
                kwargs.get("text_path", "normal"),
                kwargs.get("add_crown", False),
                kwargs.get("font_choice", "classic"),
                kwargs.get("line_width", .45),
            )
            return build_stamp_from_text_blender(**kwargs)
        except Exception as exc:
            blender_error = exc
            logger.exception("Blender stamp text engine failed")
            if mode == "blender_strict":
                raise

    legacy_kwargs = dict(kwargs)
    crown_requested = bool(legacy_kwargs.pop("add_crown", False))
    if crown_requested:
        if blender_error is not None:
            raise RuntimeError(f"Не удалось построить корону Blender-движком: {blender_error}") from blender_error
        raise RuntimeError("Корона требует Blender-движок, но Blender недоступен в контейнере.")

    logger.info("TEXT STAMP ENGINE: legacy stamp_v172 fallback (compat kwargs sanitized)")
    return _build_stamp_from_text_legacy(**legacy_kwargs)
