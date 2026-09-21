"""CakeStampBot v2.4.4 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes_v240
from ui_fix_v243 import apply_fixes as apply_ui_fixes_v243

# v2.4.4: the former Comic option now uses bundled Bad Script and is shown as
# a handwritten font. Existing `comic` session values remain compatible.
# GOST Type A and the v2.4.0 crown/performance/topper behavior are preserved.
app.VERSION = "2.4.4"
apply_ui_fixes_v240(app)
apply_ui_fixes_v243(app)

if __name__ == "__main__":
    app.main()
