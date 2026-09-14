import logging
import os

from .stamp_v172 import build_stamp_from_text as _build_stamp_from_text_legacy
from .stamp_engine import build_stamp_from_image
from .topper_engine import build_topper_from_text
from .blender_text_engine import build_stamp_from_text_blender, blender_available

logger = logging.getLogger("CakeStampEngine.Dispatch")


def build_stamp_from_text(**kwargs):
    """Use Blender for straight text stamps when available; otherwise fall back safely."""
    mode = os.getenv("STAMP_TEXT_ENGINE", "auto").strip().lower()
    text_path = str(kwargs.get("text_path", "normal") or "normal").lower()

    wants_blender = mode in {"auto", "blender", "blender_strict"}
    supported = text_path == "normal"

    if wants_blender and supported and blender_available():
        try:
            logger.info("TEXT ENGINE: Blender v2.0.0-alpha")
            return build_stamp_from_text_blender(**kwargs)
        except Exception:
            logger.exception("Blender text engine failed")
            if mode == "blender_strict":
                raise

    logger.info("TEXT ENGINE: legacy stamp_v172 fallback")
    return _build_stamp_from_text_legacy(**kwargs)
