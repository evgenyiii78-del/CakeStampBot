"""CakeStampBot v2.2.1 — compact interactive stamp UI + reliable callback routing."""
import json, os
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import bot_legacy as legacy
VERSION="2.2.1"
ACCESS_FILE=Path(os.getenv("DATA_DIR","data"))/"allowed_users.json"; ACCESS_FILE.parent.mkdir(parents=True,exist_ok=True)
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
 if u.callback_query:await u.callback_query.answer("Доступ закрыт",show_alert=True)
 if u.effective_message:await u.effective_message.reply_text(f"🔒 Доступ закрыт.\nВаш Telegram ID: {uid}")
def guarded(fn):
 async def w(u,c):
  if not allowed(u.effective_user.id if u.effective_user else 0):return await deny(u)
  return await fn(u,c)
 return w
def mark(s,on):return "✓ "+s if on else s
def defaults(c):
 legacy.ensure_stamp_defaults(c);d=c.user_data
 if float(d.get("text_size_mm",12))<10:d["text_size_mm"]=12.0
 d.setdefault("base_shape","round");d.setdefault("crown_position","top");d.setdefault("add_crown",False);d.setdefault("add_heart",False);d.setdefault("layout_mode","separate")
def source_kb():return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст",callback_data="ui:source:text")],[InlineKeyboardButton("🖼 Картинка / логотип",callback_data="ui:source:image")]])
def panel_text(c):
 defaults(c);d=c.user_data;p={"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d.get("text_path"),"Обычный");e=[]
 if d.get("add_heart"):e.append("❤️ сердце")
 if d.get("add_crown"):e.append("👑 корона")
 if not e:e=["без дополнений"]
 shape="Круг" if d.get("base_shape")=="round" else "Прямоугольник";lines=["🍰 НАСТРОЙКИ ШТАМПА",""]
 if d.get("source","text")=="text":lines += [f"📝 {d.get('text','')}",""]
 lines += [f"✨ Дополнения: {', '.join(e)}"]
 if d.get("add_crown"):lines.append("👑 Положение: "+("сверху" if d.get("crown_position")=="top" else "снизу"))
 lines += [f"📏 Подложка: {d.get('base_size','105')} мм · {shape}"]
 if d.get("source","text")=="text":lines += [f"🔤 {legacy.stamp_font_name(c)} · {float(d.get('text_size_mm',12)):g} мм · {p}"]
 lines += ["✏️ Линия: 0.25 мм",f"🧩 3MF: {'Отдельно' if d.get('layout_mode')=='separate' else 'Собрать'}","","Выбирай параметры кнопками ниже 👇"]
 return "\n".join(lines)
def panel_kb(c):
 defaults(c);d=c.user_data;s=str(d.get("base_size","105"));sh=d.get("base_shape","round");p=d.get("text_path","normal");f=d.get("font_choice","classic");h=float(d.get("text_size_mm",12));cp=d.get("crown_position","top")
 r=[[InlineKeyboardButton(mark("❤️ Сердце",d.get("add_heart")),callback_data="qs:heart"),InlineKeyboardButton(mark("👑 Корона",d.get("add_crown")),callback_data="qs:crown")],[InlineKeyboardButton("✨ Без дополнений",callback_data="ui:noextras")]]
 if d.get("add_crown"):r.append([InlineKeyboardButton(mark("👑 Сверху",cp=="top"),callback_data="ui:crownpos:top"),InlineKeyboardButton(mark("⬇️ Снизу",cp=="bottom"),callback_data="ui:crownpos:bottom")])
 r += [[InlineKeyboardButton(mark("60 мм",s=="60"),callback_data="qs:size:60"),InlineKeyboardButton(mark("105 мм",s=="105"),callback_data="qs:size:105"),InlineKeyboardButton(mark("145 мм",s=="145"),callback_data="qs:size:145")],[InlineKeyboardButton(mark("⭕ Круг",sh=="round"),callback_data="ui:shape:round"),InlineKeyboardButton(mark("▭ Прямоугольник",sh=="rect"),callback_data="ui:shape:rect")]]
 if d.get("source","text")=="text":r += [[InlineKeyboardButton(mark("Classic",f=="classic"),callback_data="qs:font:classic"),InlineKeyboardButton(mark("Comic",f=="comic"),callback_data="qs:font:comic"),InlineKeyboardButton(mark("GOST",f=="gost"),callback_data="qs:font:gost")],[InlineKeyboardButton(mark("10",h==10),callback_data="qs:h:10"),InlineKeyboardButton(mark("12",h==12),callback_data="qs:h:12"),InlineKeyboardButton(mark("14",h==14),callback_data="qs:h:14"),InlineKeyboardButton(mark("16 мм",h==16),callback_data="qs:h:16")],[InlineKeyboardButton(mark("Обычный",p=="normal"),callback_data="qs:path:normal"),InlineKeyboardButton(mark("Сверху",p=="top"),callback_data="qs:path:top")],[InlineKeyboardButton(mark("Снизу",p=="bottom"),callback_data="qs:path:bottom"),InlineKeyboardButton(mark("По окружности",p=="full"),callback_data="qs:path:full")]]
 r += [[InlineKeyboardButton(mark("🧩 Отдельно",d.get("layout_mode")=="separate"),callback_data="qs:layout")],[InlineKeyboardButton("✅ СОЗДАТЬ ШТАМП",callback_data="create")],[InlineKeyboardButton("↩️ Назад в меню",callback_data="restart")]]
 return InlineKeyboardMarkup(r)
async def show(target,c):
 t=panel_text(c);k=panel_kb(c)
 if hasattr(target,"edit_message_text"):await target.edit_message_text(t,reply_markup=k)
 else:await target.reply_text(t,reply_markup=k)
legacy.stamp_settings_text=panel_text;legacy.stamp_quick_keyboard=panel_kb;legacy.show_stamp_settings=show
async def start(u,c):c.user_data.clear();await u.message.reply_text(f"CakeStampBot v{VERSION}\n\nВыбери действие в меню ниже 👇",reply_markup=legacy.main_menu_keyboard())
async def stamp_cmd(u,c):c.user_data.clear();c.user_data["mode"]="stamp";await u.message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_kb())
async def help_cmd(u,c):await u.message.reply_text(f"CakeStampBot v{VERSION}\n\n🍰 Штамп — компактная панель настроек.\n👑 Корона и ❤️ сердце.\n🎂 Топпер без изменений.",reply_markup=legacy.main_menu_keyboard())
async def callback(u,c):
 q=u.callback_query;data=q.data or ""
 try:
  if data=="ui:source:text":
   await q.answer();c.user_data.clear();c.user_data.update(mode="stamp",source="text");return await q.edit_message_text("✍️ Напиши текст штампа одним сообщением.")
  if data=="ui:source:image":
   await q.answer();c.user_data.clear();c.user_data.update(mode="stamp",source="image");return await q.edit_message_text("🖼 Пришли картинку или логотип.")
  if data=="ui:noextras":await q.answer();c.user_data["add_heart"]=False;c.user_data["add_crown"]=False;return await show(q,c)
  if data.startswith("ui:crownpos:"):await q.answer();c.user_data["crown_position"]=data.rsplit(":",1)[1];return await show(q,c)
  if data.startswith("ui:shape:"):await q.answer();c.user_data["base_shape"]=data.rsplit(":",1)[1];return await show(q,c)
  return await legacy.on_callback(u,c)
 except Exception as e:
  legacy.logger.exception("callback failed: %s",data)
  try:await q.answer("Ошибка кнопки. Попробуй ещё раз.",show_alert=True)
  except Exception:pass
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
async def post_init(app):await legacy.post_init(app);await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")]);legacy.logger.info("CakeStampBot v%s UI started",VERSION)
def main():
 app=Application.builder().token(legacy.BOT_TOKEN).post_init(post_init).post_shutdown(legacy.post_shutdown).build();app.add_handler(CommandHandler("start",guarded(start)));app.add_handler(CommandHandler("help",guarded(help_cmd)));app.add_handler(CommandHandler("stamp",guarded(stamp_cmd)));app.add_handler(CommandHandler("topper",guarded(legacy.topper_cmd)));app.add_handler(CommandHandler("queue",guarded(legacy.queue_cmd)));app.add_handler(CommandHandler("users",users_cmd));app.add_handler(CommandHandler("adduser",adduser));app.add_handler(CommandHandler("deluser",deluser));app.add_handler(CallbackQueryHandler(guarded(callback)));app.add_handler(MessageHandler(filters.PHOTO,guarded(legacy.on_photo)));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,guarded(legacy.on_text)));app.add_error_handler(legacy.error_handler);app.run_polling()
if __name__=="__main__":main()
