"""CakeStampBot v2.4.0 release entrypoint."""
import bot_v182 as app
from ui_fix_v240 import apply_fixes as apply_ui_fixes

# v2.4.0: larger approved crown, faster stamp vector pipeline,
# compact settings chat; topper remains unchanged.
app.VERSION = "2.4.0"
apply_ui_fixes(app)

if __name__ == "__main__":
    app.main()
