"""CakeStampBot v2.4.1 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes

# v2.4.1: Comic Sans MS and GOST Type A keep native TTF outlines;
# v2.4.0 crown/performance/UI fixes and topper behavior are preserved.
app.VERSION = "2.4.1"
apply_ui_fixes(app)

if __name__ == "__main__":
    app.main()
