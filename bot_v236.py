"""CakeStampBot v2.4.2 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes_v240
from ui_fix_v242 import apply_fixes as apply_ui_fixes_v242

# v2.4.2: Comic Sans MS and GOST Type A are traced from their real TTF
# contours with practical selectable thin stamp widths (0.35-0.60 mm).
# v2.4.0 crown/performance/UI fixes and topper behavior are preserved.
app.VERSION = "2.4.2"
apply_ui_fixes_v240(app)
apply_ui_fixes_v242(app)

if __name__ == "__main__":
    app.main()
