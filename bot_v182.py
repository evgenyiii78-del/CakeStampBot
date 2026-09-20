"""CakeStampBot v2.3.2 — ReplyKeyboard stamp UI with explicit 3MF layout."""
import json, os, uuid
from pathlib import Path
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import bot_legacy as legacy
VERSION="2.3.2"
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
def allowed(uid):return int(uid) in ADMIN_IDS|ENV_ALLOWED_IDS|_load()
async def deny(u):
 uid=u.effective_user.id if u.effective_user else 0
 if u.callback_query:
  try:await u.callback_query.answer("Доступ закрыт",show_alert=True)
  except Exception:pass
 if u.effective_message:await u.effective_message.reply_text(f"🔒 Доступ закрыт.\nВаш Telegram ID: {uid}")
def guarded(fn):
 async def w(u,c):
  if not allowed(u.effective_user.id if u.effective_user else 0):return await deny(u)
  return await fn(u,c)
 return w
def defaults(c):
 legacy.ensure_stamp_defaults(c);d=c.user_data;d["mode"]="stamp"
 if float(d.get("text_size_mm",12))<10:d["text_size_mm"]=12.0
 d.setdefault("source","text");d.setdefault("base_shape","round");d.setdefault("crown_position","top");d.setdefault("add_crown",False);d.setdefault("add_heart",False);d.setdefault("layout_mode","separate")
def source_kb():return ReplyKeyboardMarkup([["✍️ Текст","🖼 Картинка / логотип"],["↩️ Главное меню"]],resize_keyboard=True)
def stamp_kb():return ReplyKeyboardMarkup([["❤️ Сердце","👑 Корона","✨ Без дополнений"],["📏 60 мм","📏 105 мм","📏 145 мм"],["⭕ Круг","▭ Прямоугольник"],["🔤 Classic","🔤 Comic","🔤 GOST"],["↕️ 10 мм","↕️ 12 мм","↕️ 14 мм","↕️ 16 мм"],["↔️ Обычный","⬆️ Сверху","⬇️ Снизу","⭕ По окружности"],["🧩 Отдельно","🔗 Собрать"],["✅ СОЗДАТЬ ШТАМП"],["↩️ Главное меню"]],resize_keyboard=True)
def panel_text(c):
 defaults(c);d=c.user_data;p={"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d.get("text_path"),"Обычный");e=[]
 if d.get("add_heart"):e.append("❤️ сердце")
 if d.get("add_crown"):e.append("👑 корона")
 if not e:e=["без дополнений"]
 shape="Круг" if d.get("base_shape")=="round" else "Прямоугольник";src=f"📝 {d.get('text','')}" if d.get("source")=="text" else "🖼 Картинка / логотип";layout="🧩 Отдельно" if d.get("layout_mode")=="separate" else "🔗 Собрать"
 lines=["🍰 НАСТРОЙКИ ШТАМПА",src,"",f"✨ Дополнения: {', '.join(e)}",f"📏 Подложка: {d.get('base_size','105')} мм · {shape}"]
 if d.get("source")=="text":lines.append(f"🔤 {legacy.stamp_font_name(c)} · {float(d.get('text_size_mm',12)):g} мм · {p}")
 lines += ["✏️ Линия: 0.25 мм",f"📦 Режим 3MF: {layout}",f"CakeStampBot v{VERSION}","","Выбери параметры, затем нажми ✅ СОЗДАТЬ ШТАМП."]
 return "\n".join(lines)
async def show(message,c):await message.reply_text(panel_text(c),reply_markup=stamp_kb())
async def start(u,c):c.user_data.clear();await u.message.reply_text(f"CakeStampBot v{VERSION}\n\nВыбери действие в меню ниже 👇",reply_markup=legacy.main_menu_keyboard())
async def stamp_cmd(u,c):c.user_data.clear();c.user_data.update(mode="stamp",step="source");await u.effective_message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_kb())
async def help_cmd(u,c):await u.message.reply_text(f"CakeStampBot v{VERSION}\nШтамп использует обычные Telegram-кнопки.\n🧩 Отдельно и 🔗 Собрать выбираются явно.\nТоппер без изменений.",reply_markup=legacy.main_menu_keyboard())
async def text_router(u,c):
 text=(u.message.text or "").strip();d=c.user_data;legacy.logger.info("v%s TEXT=%r mode=%s",VERSION,text,d.get("mode"))
 if text=="🍰 Штамп":return await stamp_cmd(u,c)
 if text=="🎂 Топпер":return await legacy.topper_cmd(u,c)
 if text=="📋 Очередь":return await legacy.queue_cmd(u,c)
 if text=="ℹ️ Помощь":return await help_cmd(u,c)
 if text=="↩️ Главное меню":d.clear();return await u.message.reply_text("Главное меню:",reply_markup=legacy.main_menu_keyboard())
 if text in ("✍️ Текст","Текст") and d.get("mode")=="stamp":d.update(source="text",step="text");return await u.message.reply_text("✍️ Напиши текст штампа одним сообщением.",reply_markup=ReplyKeyboardRemove())
 if text in ("🖼 Картинка / логотип","Картинка / логотип") and d.get("mode")=="stamp":d.update(source="image",step="photo");return await u.message.reply_text("🖼 Пришли картинку или логотип.",reply_markup=ReplyKeyboardRemove())
 if d.get("mode")!="stamp":return await legacy.on_text(u,c)
 if d.get("step")=="text":d["text"]=text;d["step"]="settings";defaults(c);return await show(u.message,c)
 if d.get("source")=="image" and d.get("step")=="photo":return await u.message.reply_text("🖼 Жду изображение.")
 defaults(c);d["step"]="settings"
 if text=="❤️ Сердце":d["add_heart"]=not bool(d.get("add_heart"))
 elif text=="👑 Корона":d["add_crown"]=not bool(d.get("add_crown"))
 elif text=="✨ Без дополнений":d["add_heart"]=False;d["add_crown"]=False
 elif text in ("📏 60 мм","📏 105 мм","📏 145 мм"):v=text.split()[1];d["base_size"]=v;d["stamp_size"]=v
 elif text=="⭕ Круг":d["base_shape"]="round"
 elif text=="▭ Прямоугольник":d["base_shape"]="rect"
 elif text.startswith("🔤 "):d["font_choice"]={"Classic":"classic","Comic":"comic","GOST":"gost"}.get(text[2:].strip(),"classic")
 elif text.startswith("↕️ "):d["text_size_mm"]=float(text.split()[1])
 elif text=="↔️ Обычный":d["text_path"]="normal"
 elif text=="⬆️ Сверху":d["text_path"]="top"
 elif text=="⬇️ Снизу":d["text_path"]="bottom"
 elif text=="⭕ По окружности":d["text_path"]="full"
 elif text=="🧩 Отдельно":d["layout_mode"]="separate";await u.message.reply_text("🧩 Выбран режим: элементы 3MF отдельно.",reply_markup=stamp_kb())
 elif text=="🔗 Собрать":d["layout_mode"]="assembled";await u.message.reply_text("🔗 Выбран режим: собрать элементы на подложке. Теперь нажми ✅ СОЗДАТЬ ШТАМП.",reply_markup=stamp_kb())
 elif text=="✅ СОЗДАТЬ ШТАМП":await u.message.reply_text(f"⏳ Создаю штамп. Режим: {'Собрать' if d.get('layout_mode')=='assembled' else 'Отдельно'}…",reply_markup=stamp_kb());return await legacy.enqueue_job(u.message,c)
 else:return await u.message.reply_text("Используй кнопки настроек ниже.",reply_markup=stamp_kb())
 return await show(u.message,c)
async def photo_router(u,c):
 if c.user_data.get("mode")!="stamp" or c.user_data.get("source")!="image":return await legacy.on_photo(u,c)
 f=await u.message.photo[-1].get_file();p=legacy.UPLOAD_DIR/f"{uuid.uuid4().hex[:10]}.jpg";await f.download_to_drive(str(p));c.user_data["image_path"]=str(p);c.user_data["step"]="settings";defaults(c);return await show(u.message,c)
async def legacy_callback(u,c):
 if c.user_data.get("mode")=="stamp":
  try:await u.callback_query.answer("Старая кнопка. Нажми /start.",show_alert=True)
  except Exception:pass
  return
 return await legacy.on_callback(u,c)
async def users_cmd(u,c):
 if u.effective_user.id not in ADMIN_IDS:return await deny(u)
 await u.message.reply_text("🔐 Доступ:\n"+"\n".join(f"• {x}" for x in sorted(ADMIN_IDS|ENV_ALLOWED_IDS|_load())))
async def adduser(u,c):
 if u.effective_user.id not in ADMIN_IDS:return await deny(u)
 try:uid=int(c.args[0])
 except:return await u.message.reply_text("/adduser 123456789")
 ids=_load();ids.add(uid);_save(ids);await u.message.reply_text(f"✅ Доступ выдан: {uid}")
async def deluser(u,c):
 if u.effective_user.id not in ADMIN_IDS:return await deny(u)
 try:uid=int(c.args[0])
 except:return await u.message.reply_text("/deluser 123456789")
 if uid in ADMIN_IDS:return await u.message.reply_text("❌ Нельзя удалить администратора")
 ids=_load();ids.discard(uid);_save(ids);await u.message.reply_text(f"🚫 Доступ закрыт: {uid}")
async def post_init(app):await legacy.post_init(app);await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")]);legacy.logger.info("CakeStampBot v%s started",VERSION)
def main():
 app=Application.builder().token(legacy.BOT_TOKEN).post_init(post_init).post_shutdown(legacy.post_shutdown).build();app.add_handler(CommandHandler("start",guarded(start)));app.add_handler(CommandHandler("help",guarded(help_cmd)));app.add_handler(CommandHandler("stamp",guarded(stamp_cmd)));app.add_handler(CommandHandler("topper",guarded(legacy.topper_cmd)));app.add_handler(CommandHandler("queue",guarded(legacy.queue_cmd)));app.add_handler(CommandHandler("users",users_cmd));app.add_handler(CommandHandler("adduser",adduser));app.add_handler(CommandHandler("deluser",deluser));app.add_handler(CallbackQueryHandler(guarded(legacy_callback)));app.add_handler(MessageHandler(filters.PHOTO,guarded(photo_router)));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,guarded(text_router)));app.add_error_handler(legacy.error_handler);app.run_polling(drop_pending_updates=True)
if __name__=="__main__":main()
