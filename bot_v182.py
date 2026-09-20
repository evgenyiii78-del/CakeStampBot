"""CakeStampBot v2.3.0 — single callback router for stamp UI."""
import json, os, uuid
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import bot_legacy as legacy

VERSION="2.3.0"
ACCESS_FILE=Path(os.getenv("DATA_DIR","data"))/"allowed_users.json"
ACCESS_FILE.parent.mkdir(parents=True,exist_ok=True)

def _ids(name):
    out=set()
    for x in os.getenv(name,"").replace(";",",").split(","):
        try:
            if x.strip(): out.add(int(x.strip()))
        except ValueError: legacy.logger.warning("Invalid %s: %s",name,x)
    return out
ADMIN_IDS=_ids("ADMIN_USER_IDS"); ENV_ALLOWED_IDS=_ids("ALLOWED_USER_IDS")
def _load():
    try: return {int(x) for x in json.loads(ACCESS_FILE.read_text(encoding="utf-8"))} if ACCESS_FILE.exists() else set()
    except Exception: legacy.logger.exception("access file"); return set()
def _save(ids): ACCESS_FILE.write_text(json.dumps(sorted(ids),indent=2),encoding="utf-8")
def allowed(uid): return int(uid) in ADMIN_IDS|ENV_ALLOWED_IDS|_load()
async def deny(u):
    uid=u.effective_user.id if u.effective_user else 0
    if u.callback_query:
        try: await u.callback_query.answer("Доступ закрыт",show_alert=True)
        except Exception: pass
    if u.effective_message: await u.effective_message.reply_text(f"🔒 Доступ закрыт.\nВаш Telegram ID: {uid}")
def guarded(fn):
    async def w(u,c):
        if not allowed(u.effective_user.id if u.effective_user else 0): return await deny(u)
        return await fn(u,c)
    return w

def mark(s,on): return "✓ "+s if on else s
def defaults(c):
    legacy.ensure_stamp_defaults(c); d=c.user_data
    d["mode"]="stamp"
    if float(d.get("text_size_mm",12))<10: d["text_size_mm"]=12.0
    d.setdefault("source","text"); d.setdefault("base_shape","round"); d.setdefault("crown_position","top")
    d.setdefault("add_crown",False); d.setdefault("add_heart",False); d.setdefault("layout_mode","separate")
def source_kb():
    return ReplyKeyboardMarkup([["✍️ Текст","🖼 Картинка / логотип"],["↩️ Главное меню"]],resize_keyboard=True)
def panel_text(c):
    defaults(c); d=c.user_data
    p={"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d.get("text_path"),"Обычный")
    e=[]
    if d.get("add_heart"): e.append("❤️ сердце")
    if d.get("add_crown"): e.append("👑 корона")
    if not e: e=["без дополнений"]
    shape="Круг" if d.get("base_shape")=="round" else "Прямоугольник"
    lines=["🍰 НАСТРОЙКИ ШТАМПА",""]
    if d.get("source")=="text": lines += [f"📝 {d.get('text','')}",""]
    else: lines += ["🖼 Источник: картинка / логотип",""]
    lines += [f"✨ Дополнения: {', '.join(e)}",f"📏 Подложка: {d.get('base_size','105')} мм · {shape}"]
    if d.get("source")=="text": lines += [f"🔤 {legacy.stamp_font_name(c)} · {float(d.get('text_size_mm',12)):g} мм · {p}"]
    lines += ["✏️ Линия: 0.25 мм",f"🧩 3MF: {'Отдельно' if d.get('layout_mode')=='separate' else 'Собрать'}","",f"CakeStampBot v{VERSION}","Выбирай параметры кнопками ниже 👇"]
    return "\n".join(lines)
def panel_kb(c):
    defaults(c); d=c.user_data; s=str(d.get("base_size","105")); sh=d.get("base_shape","round"); p=d.get("text_path","normal"); f=d.get("font_choice","classic"); h=float(d.get("text_size_mm",12))
    r=[[InlineKeyboardButton(mark("❤️ Сердце",bool(d.get("add_heart"))),callback_data="stamp:heart"),InlineKeyboardButton(mark("👑 Корона",bool(d.get("add_crown"))),callback_data="stamp:crown")],[InlineKeyboardButton("✨ Без дополнений",callback_data="stamp:noextras")],[InlineKeyboardButton(mark("60 мм",s=="60"),callback_data="stamp:size:60"),InlineKeyboardButton(mark("105 мм",s=="105"),callback_data="stamp:size:105"),InlineKeyboardButton(mark("145 мм",s=="145"),callback_data="stamp:size:145")],[InlineKeyboardButton(mark("⭕ Круг",sh=="round"),callback_data="stamp:shape:round"),InlineKeyboardButton(mark("▭ Прямоугольник",sh=="rect"),callback_data="stamp:shape:rect")]]
    if d.get("source")=="text":
        r += [[InlineKeyboardButton(mark("Classic",f=="classic"),callback_data="stamp:font:classic"),InlineKeyboardButton(mark("Comic",f=="comic"),callback_data="stamp:font:comic"),InlineKeyboardButton(mark("GOST",f=="gost"),callback_data="stamp:font:gost")],[InlineKeyboardButton(mark("10",h==10),callback_data="stamp:h:10"),InlineKeyboardButton(mark("12",h==12),callback_data="stamp:h:12"),InlineKeyboardButton(mark("14",h==14),callback_data="stamp:h:14"),InlineKeyboardButton(mark("16 мм",h==16),callback_data="stamp:h:16")],[InlineKeyboardButton(mark("Обычный",p=="normal"),callback_data="stamp:path:normal"),InlineKeyboardButton(mark("Сверху",p=="top"),callback_data="stamp:path:top")],[InlineKeyboardButton(mark("Снизу",p=="bottom"),callback_data="stamp:path:bottom"),InlineKeyboardButton(mark("По окружности",p=="full"),callback_data="stamp:path:full")]]
    r += [[InlineKeyboardButton(mark("🧩 Отдельно",d.get("layout_mode")=="separate"),callback_data="stamp:layout")],[InlineKeyboardButton("✅ СОЗДАТЬ ШТАМП",callback_data="stamp:create")],[InlineKeyboardButton("↩️ Назад в меню",callback_data="stamp:restart")]]
    return InlineKeyboardMarkup(r)
async def show(target,c):
    text=panel_text(c); kb=panel_kb(c)
    if hasattr(target,"edit_message_text"): await target.edit_message_text(text,reply_markup=kb)
    else: await target.reply_text(text,reply_markup=kb)

async def start(u,c):
    c.user_data.clear(); await u.message.reply_text(f"CakeStampBot v{VERSION}\n\nВыбери действие в меню ниже 👇",reply_markup=legacy.main_menu_keyboard())
async def stamp_cmd(u,c):
    c.user_data.clear(); c.user_data.update(mode="stamp",step="source")
    await u.effective_message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_kb())
async def help_cmd(u,c): await u.message.reply_text(f"CakeStampBot v{VERSION}\n\n🍰 Штамп — единый обработчик кнопок.\n👑 Корона и ❤️ сердце.\n🎂 Топпер без изменений.",reply_markup=legacy.main_menu_keyboard())

async def callback(u,c):
    q=u.callback_query; data=q.data or ""
    legacy.logger.info("v%s CALLBACK data=%s uid=%s mode=%s",VERSION,data,u.effective_user.id if u.effective_user else 0,c.user_data.get("mode"))
    try:
        await q.answer()
        # Main mode selector. No delegation for stamp.
        if data=="mode:stamp":
            c.user_data.clear(); c.user_data.update(mode="stamp",step="source")
            return await q.edit_message_text("Режим: 🍰 Штамп. Выбери источник в меню снизу.")
        if data=="mode:topper":
            c.user_data.clear(); c.user_data.update(mode="topper",source="text")
            return await q.edit_message_text("Режим: 🎂 Топпер. Напиши текст для топпера.")

        # Entire stamp panel is handled HERE and nowhere else.
        if data.startswith("stamp:"):
            defaults(c); parts=data.split(":"); action=parts[1]
            if action=="heart": c.user_data["add_heart"]=not bool(c.user_data.get("add_heart"))
            elif action=="crown": c.user_data["add_crown"]=not bool(c.user_data.get("add_crown"))
            elif action=="noextras": c.user_data["add_heart"]=False; c.user_data["add_crown"]=False
            elif action=="size": c.user_data["base_size"]=parts[2]; c.user_data["stamp_size"]=parts[2]
            elif action=="shape": c.user_data["base_shape"]=parts[2]
            elif action=="font": c.user_data["font_choice"]=parts[2]
            elif action=="h": c.user_data["text_size_mm"]=float(parts[2])
            elif action=="path": c.user_data["text_path"]=parts[2]
            elif action=="layout": c.user_data["layout_mode"]="assembled" if c.user_data.get("layout_mode")=="separate" else "separate"
            elif action=="create":
                legacy.logger.info("v%s ENQUEUE stamp uid=%s",VERSION,u.effective_user.id if u.effective_user else 0)
                return await legacy.enqueue_job(q.message,c)
            elif action=="restart":
                c.user_data.clear(); return await q.edit_message_text("Настройки сброшены. Нажми 🍰 Штамп в нижнем меню.")
            else:
                legacy.logger.warning("Unknown stamp callback %s",data); return await q.message.reply_text("Неизвестная кнопка: "+data)
            return await show(q,c)

        # Topper callbacks remain compatible but are handled by this single router.
        if data.startswith("font:") and c.user_data.get("mode")=="topper":
            c.user_data["font_choice"]=data.split(":",1)[1]; legacy.ensure_topper_defaults(c)
            return await q.edit_message_text("Выбери ширину топпера:",reply_markup=legacy.topper_width_keyboard())
        if data.startswith("topper_width:"):
            legacy.ensure_topper_defaults(c); c.user_data["topper_width"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери высоту топпера:",reply_markup=legacy.topper_text_height_keyboard())
        if data.startswith("topper_text_h:"):
            c.user_data["topper_text_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери толщину подложки под буквами:",reply_markup=legacy.topper_backing_keyboard())
        if data.startswith("topper_backing:"):
            c.user_data["topper_backing_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Сколько ножек сделать?",reply_markup=legacy.topper_legs_keyboard())
        if data.startswith("topper_legs:"):
            c.user_data["topper_legs"]=data.split(":",1)[1]; return await q.edit_message_text(legacy.topper_summary_text(c),reply_markup=legacy.create_keyboard())
        if data=="create" and c.user_data.get("mode")=="topper": return await legacy.enqueue_job(q.message,c)
        if data=="restart": c.user_data.clear(); return await q.edit_message_text("Настройки сброшены. Используй нижнее меню.")
        legacy.logger.warning("UNHANDLED callback=%s",data)
        await q.message.reply_text("Кнопка не распознана. Нажми /start.")
    except Exception as exc:
        legacy.logger.exception("v%s callback failed data=%s",VERSION,data)
        try: await q.message.reply_text(f"Ошибка кнопки [{data}]: {type(exc).__name__}: {exc}")
        except Exception: pass

async def text_router(u,c):
    text=(u.message.text or "").strip()
    if text=="🍰 Штамп": return await stamp_cmd(u,c)
    if text=="🎂 Топпер": return await legacy.topper_cmd(u,c)
    if text=="📋 Очередь": return await legacy.queue_cmd(u,c)
    if text=="ℹ️ Помощь": return await help_cmd(u,c)
    if text=="↩️ Главное меню": c.user_data.clear(); return await u.message.reply_text("Главное меню:",reply_markup=legacy.main_menu_keyboard())
    if text in ("✍️ Текст","Текст") and c.user_data.get("mode")=="stamp":
        c.user_data.update(source="text",step="text"); return await u.message.reply_text("✍️ Напиши текст штампа одним сообщением.",reply_markup=ReplyKeyboardRemove())
    if text in ("🖼 Картинка / логотип","Картинка / логотип") and c.user_data.get("mode")=="stamp":
        c.user_data.update(source="image",step="photo"); return await u.message.reply_text("🖼 Пришли картинку или логотип.",reply_markup=ReplyKeyboardRemove())
    if c.user_data.get("mode")=="stamp" and c.user_data.get("source")=="text":
        c.user_data["text"]=text; defaults(c); return await show(u.message,c)
    return await legacy.on_text(u,c)

async def photo_router(u,c):
    if c.user_data.get("mode")!="stamp" or c.user_data.get("source")!="image": return await legacy.on_photo(u,c)
    f=await u.message.photo[-1].get_file(); p=legacy.UPLOAD_DIR/f"{uuid.uuid4().hex[:10]}.jpg"; await f.download_to_drive(str(p))
    c.user_data["image_path"]=str(p); defaults(c); return await show(u.message,c)

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
async def post_init(app):
    await legacy.post_init(app); await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")]); legacy.logger.info("CakeStampBot v%s started — SINGLE CALLBACK ROUTER",VERSION)
def main():
    app=Application.builder().token(legacy.BOT_TOKEN).post_init(post_init).post_shutdown(legacy.post_shutdown).build()
    app.add_handler(CommandHandler("start",guarded(start))); app.add_handler(CommandHandler("help",guarded(help_cmd))); app.add_handler(CommandHandler("stamp",guarded(stamp_cmd))); app.add_handler(CommandHandler("topper",guarded(legacy.topper_cmd))); app.add_handler(CommandHandler("queue",guarded(legacy.queue_cmd)))
    app.add_handler(CommandHandler("users",users_cmd)); app.add_handler(CommandHandler("adduser",adduser)); app.add_handler(CommandHandler("deluser",deluser))
    app.add_handler(CallbackQueryHandler(guarded(callback)))
    app.add_handler(MessageHandler(filters.PHOTO,guarded(photo_router))); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,guarded(text_router))); app.add_error_handler(legacy.error_handler)
    app.run_polling(drop_pending_updates=True)
if __name__=="__main__":main()
