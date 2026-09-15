import logging
import os

from .stamp_v172 import build_stamp_from_text as _build_stamp_from_text_legacy
from .stamp_engine import build_stamp_from_image
from .topper_engine import build_topper_from_text
from .blender_text_engine import build_stamp_from_text_blender, blender_available

logger = logging.getLogger("CakeStampEngine.Dispatch")


def build_stamp_from_text(**kwargs):
    """v2.1.0: Blender is primary for every text-stamp path; legacy is fallback."""
    mode=os.getenv("STAMP_TEXT_ENGINE","auto").strip().lower()
    wants_blender=mode in {"auto","blender","blender_strict"}

    if wants_blender and blender_available():
        try:
            logger.info("TEXT STAMP ENGINE: Blender v2.1.0 | path=%s",kwargs.get("text_path","normal"))
            return build_stamp_from_text_blender(**kwargs)
        except Exception:
            logger.exception("Blender stamp text engine failed; using legacy fallback")
            if mode=="blender_strict": raise

    logger.info("TEXT STAMP ENGINE: legacy stamp_v172 fallback")
    return _build_stamp_from_text_legacy(**kwargs)
