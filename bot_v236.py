"""CakeStampBot v2.3.6 release entrypoint."""
import bot_v182 as app

# Keep the proven UI/router intact while making the deployed build visible
# in /start, settings and logs.
app.VERSION = "2.3.6"

if __name__ == "__main__":
    app.main()
