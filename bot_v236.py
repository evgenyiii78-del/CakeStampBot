"""CakeStampBot v2.4.3 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes_v240
from ui_fix_v243 import apply_fixes as apply_ui_fixes_v243

# v2.4.3: Comic Sans MS and GOST Type A use a high-resolution medial-axis
# single-line conversion from the real TTF glyphs. No double contour letters.
# v2.4.0 crown/performance fixes and topper behavior are preserved.
app.VERSION = "2.4.3"
apply_ui_fixes_v240(app)
apply_ui_fixes_v243(app)

if __name__ == "__main__":
    app.main()
