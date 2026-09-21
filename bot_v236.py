"""CakeStampBot v2.4.1 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes_v240
from ui_fix_v241 import apply_fixes as apply_ui_fixes_v241

# v2.4.1: Comic Sans MS and GOST Type A keep native TTF outlines;
# practical 0.35/0.40/0.45/0.60 mm stamp widths are selectable again.
# v2.4.0 crown/performance/UI fixes and topper behavior are preserved.
app.VERSION = "2.4.1"
apply_ui_fixes_v240(app)
apply_ui_fixes_v241(app)

if __name__ == "__main__":
    app.main()
