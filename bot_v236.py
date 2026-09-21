"""CakeStampBot v2.3.7 release entrypoint."""
import bot_v182 as app

# v2.3.7: local stamp-engine fix only; UI/router and topper remain unchanged.
app.VERSION = "2.3.7"

if __name__ == "__main__":
    app.main()
