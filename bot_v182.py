"""CakeStampBot v2.3.3 — ReplyKeyboard stamp UI with explicit 3MF layout."""
import json, os, uuid
from pathlib import Path
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import bot_legacy as legacy
VERSION="2.3.3"
ACCESS_FILE=Path(os.getenv("DATA_DIR","data"))/"allowed_users.json";ACCESS_FILE.parent.mkdir(parents=True,exist_ok=True)
def _ids(name):
 out=set()
 for x in os.getenv(name,"").replace(";",",").split(","):
  try:
   if x.strip():out.add(int(x.strip()))
  except ValueError:legacy.logger.warning("Invalid %s: %s",name,x)
 return out
ADMIN_IDS=_ids("ADMIN_USER_IDS");ENV_ALLOWED_IDS=_ids("ALLOWED_USER_IDS")
def _load():
 try:return {int(x) for x in json.loads(ACCESS_FILE.read_text(encoding="utf-8"))} if ACCESS_FILE.exists() else set()
 except Exception:legacy.logger.exception("access file");return set()
def _save(ids):ACCESS_FILE.write_text(json.dumps(sorted(ids),indent=2),encoding="utf-8")