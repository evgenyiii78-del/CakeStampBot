"""CakeStampBot v1.9.0 Reply-only stamp workflow + Access Control.
All stamp steps use Telegram ReplyKeyboardMarkup; no inline callbacks are required.
Stamp/topper geometry untouched.
"""
import os, json, uuid
from pathlib import Path
from telegram import ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import bot_legacy as legacy

ACCESS_FILE=Path(os.getenv("DATA_DIR","data"))/"allowed_users.json"; ACCESS_FILE.parent.mkdir(parents=True,exist_ok=True)
def _ids_from_env(name):
    out=set()
    for raw in os.getenv(name,"").replace(";",",").split(","):
        raw=raw.strip()
        if raw:
            try: out.add(int(raw))
            except ValueError: legacy.logger.warning("Invalid %s value: %s",name,raw)
    return out
ADMIN_IDS=_ids_from_env("ADMIN_USER_IDS"); ENV_ALLOWED_IDS=_ids_from_env("ALLOWED_USER_IDS")
def _load_allowed():
    try:
        if ACCESS_FILE.exists(): return {int(x) for x in json.loads(ACCESS_FILE.read_text(encoding="utf-8")) if str(x).strip()}
    except Exception: legacy.logger.exception("Failed to read access list")
    return set()
def _save_allowed(ids):
    tmp=ACCESS_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(sorted(ids),ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(ACCESS_FILE)
def is_admin(uid): return int(uid) in ADMIN_IDS
def is_allowed(uid): uid=int(uid); return uid in ADMIN_IDS or uid in ENV_ALLOWED_IDS or uid in _load_allowed()
async def deny(update):
    uid=update.effective_user.id if update.effective_user else 0; text=f"🔒 Доступ к боту закрыт.\n\nВаш Telegram ID: {uid}\nОтправьте этот ID администратору для получения доступа."
    if update.callback_query:
        await update.callback_query.answer("Доступ закрыт",show_alert=True)
    if update.effective_message: await update.effective_message.reply_text(text)
def guarded(handler):
    async def wrapper(update,context):
        if not is_allowed(update.effective_user.id if update.effective_user else 0): return await deny(update)
        return await handler(update,context)
    return wrapper

async def users_cmd(update,context):
    if not is_admin(update.effective_user.id): return await deny(update)
    all_users=sorted(ADMIN_IDS|ENV_ALLOWED_IDS|_load_allowed()); lines=["🔐 Пользователи с доступом:"]
    for x in all_users: lines.append(f"• {x}{' 👑 admin' if x in ADMIN_IDS else ''}{' (env)' if x in ENV_ALLOWED_IDS and x not in ADMIN_IDS else ''}")
    if len(lines)==1: lines.append("• список пуст")
    await update.effective_message.reply_text("\n".join(lines))
async def adduser_cmd(update,context):
    if not is_admin(update.effective_user.id): return await deny(update)
    if not context.args: return await update.effective_message.reply_text("Использование: /adduser 123456789")
    try: target=int(context.args[0])
    except ValueError: return await update.effective_message.reply_text("❌ Telegram ID должен быть числом.")
    ids=_load_allowed(); ids.add(target); _save_allowed(ids); await update.effective_message.reply_text(f"✅ Доступ выдан: {target}")
async def deluser_cmd(update,context):
    if not is_admin(update.effective_user.id): return await deny(update)
    if not context.args: return await update.effective_message.reply_text("Использование: /deluser 123456789")
    try: target=int(context.args[0])
    except ValueError: return await update.effective_message.reply_text("❌ Telegram ID должен быть числом.")
    if target in ADMIN_IDS: return await update.effective_message.reply_text("❌ Нельзя удалить администратора из ADMIN_USER_IDS.")
    ids=_load_allowed(); ids.discard(target); _save_allowed(ids); await update.effective_message.reply_text(f"🚫 Доступ закрыт: {target}")

def kb(rows): return ReplyKeyboardMarkup(rows,resize_keyboard=True)
def source_kb(): return kb([["✍️ Текст","🖼 Картинка / логотип"],["↩️ Главное меню"]])
def size_kb(): return kb([["60 мм","80 мм","105 мм"],["130 мм","145 мм"],["↩️ Главное меню"]])
def shape_kb(): return kb([["⭕ Круглая","▭ Прямоугольная"],["↩️ Главное меню"]])
def rect_kb(): return kb([["80×60","100×70"],["105×75","120×80"],["145×95"],["↩️ Главное меню"]])
def font_kb(): return kb([["Classic","Comic","GOST"],["↩️ Главное меню"]])
def height_kb(): return kb([["10 мм","11 мм","12 мм","13 мм"],["14 мм","15 мм","16 мм"],["↩️ Главное меню"]])
def path_kb(): return kb([["Обычный","Сверху"],["Снизу","По окружности"],["↩️ Главное меню"]])
def heart_kb(): return kb([["❤️ С сердцем","Без сердца"],["↩️ Главное меню"]])
def layout_kb(): return kb([["✅ Собрать","🧩 Отдельно"],["↩️ Главное меню"]])
def create_kb(): return kb([["🚀 СОЗДАТЬ 3MF"],["↩️ Главное меню"]])

def init_stamp(c,source=None):
    if source: c.user_data["source"]=source
    c.user_data["mode"]="stamp"; legacy.ensure_stamp_defaults(c)
    if float(c.user_data.get("text_size_mm",12))<10: c.user_data["text_size_mm"]=12.0

def stamp_summary(c):
    d=c.user_data; src="Текст" if d.get("source")=="text" else "Картинка"
    shape="Круг" if d.get("base_shape","round")=="round" else "Прямоугольник"
    lines=["🍰 Проверь настройки:",f"Источник: {src}",f"Размер: {d.get('base_size','105')} мм",f"Форма: {shape}"]
    if d.get("source")=="text":
        lines += [f"Текст: {d.get('text','')}",f"Шрифт: {legacy.stamp_font_name(c)}",f"Высота: {float(d.get('text_size_mm',12)):g} мм",f"Расположение: { {'normal':'Обычный','top':'Сверху','bottom':'Снизу','full':'По окружности'}.get(d.get('text_path'),'Обычный') }"]
    lines += ["Линия: 0.25 мм",f"Сердце: {'Да' if d.get('add_heart') else 'Нет'}",f"3MF: {'Собрать' if d.get('layout_mode')=='assembled' else 'Отдельно'}"]
    return "\n".join(lines)

async def start_v190(update,context):
    context.user_data.clear(); await update.message.reply_text("CakeStampBot v1.9.0\n\nВыбери действие в меню ниже 👇",reply_markup=legacy.main_menu_keyboard())
async def help_v190(update,context):
    await update.message.reply_text("Помощь CakeStampBot v1.9.0\n\n🍰 Весь мастер штампа теперь работает через нижнее меню Telegram — без кнопок в сообщениях.\n🔒 Доступ по Telegram ID.\n🎂 Топпер пока без изменений.",reply_markup=legacy.main_menu_keyboard())
async def stamp_menu(update,context):
    context.user_data.clear(); context.user_data.update(mode="stamp",step="source")
    await update.message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_kb())

async def photo_router(update,context):
    if context.user_data.get("mode")!="stamp" or context.user_data.get("source")!="image":
        return await update.message.reply_text("Сначала выбери 🍰 Штамп → 🖼 Картинка / логотип.",reply_markup=legacy.main_menu_keyboard())
    f=await update.message.photo[-1].get_file(); p=legacy.UPLOAD_DIR/f"{uuid.uuid4().hex[:10]}.jpg"; await f.download_to_drive(str(p))
    context.user_data["image_path"]=str(p); init_stamp(context,"image"); context.user_data["step"]="size"
    await update.message.reply_text("Картинку получил. Выбери размер штампа:",reply_markup=size_kb())

async def text_router(update,context):
    text=(update.message.text or "").strip(); d=context.user_data
    if text=="ℹ️ Помощь": return await help_v190(update,context)
    if text=="🍰 Штамп": return await stamp_menu(update,context)
    if text=="🎂 Топпер": return await legacy.topper_cmd(update,context)
    if text=="📋 Очередь": return await legacy.queue_cmd(update,context)
    if text=="↩️ Главное меню": d.clear(); return await update.message.reply_text("Главное меню:",reply_markup=legacy.main_menu_keyboard())
    if d.get("mode")!="stamp": return await legacy.on_text(update,context)

    step=d.get("step","source")
    if step=="source":
        if text=="✍️ Текст": d["source"]="text"; d["step"]="text"; return await update.message.reply_text("Напиши текст штампа:",reply_markup=kb([["↩️ Главное меню"]]))
        if text=="🖼 Картинка / логотип": d["source"]="image"; d["step"]="photo"; return await update.message.reply_text("Пришли картинку или логотип:",reply_markup=kb([["↩️ Главное меню"]]))
        return await update.message.reply_text("Выбери источник:",reply_markup=source_kb())
    if step=="photo": return await update.message.reply_text("Жду картинку или логотип.")
    if step=="text":
        init_stamp(context,"text"); d["text"]=text; d["step"]="size"; return await update.message.reply_text("Выбери размер штампа:",reply_markup=size_kb())
    if step=="size":
        sizes={"60 мм":"60","80 мм":"80","105 мм":"105","130 мм":"130","145 мм":"145"}
        if text not in sizes: return await update.message.reply_text("Выбери размер кнопкой ниже:",reply_markup=size_kb())
        d["stamp_size"]=sizes[text]; d["base_size"]=sizes[text]; d["step"]="shape"; return await update.message.reply_text("Выбери форму подложки:",reply_markup=shape_kb())
    if step=="shape":
        if text=="⭕ Круглая": d["base_shape"]="round"
        elif text=="▭ Прямоугольная": d["base_shape"]="rect"; d["step"]="rect"; return await update.message.reply_text("Выбери размер прямоугольной подложки:",reply_markup=rect_kb())
        else: return await update.message.reply_text("Выбери форму кнопкой ниже:",reply_markup=shape_kb())
        d["step"]="font" if d.get("source")=="text" else "heart"
        return await update.message.reply_text("Выбери шрифт:" if d["step"]=="font" else "Добавить сердечко?",reply_markup=font_kb() if d["step"]=="font" else heart_kb())
    if step=="rect":
        vals={"80×60":"80x60","100×70":"100x70","105×75":"105x75","120×80":"120x80","145×95":"145x95"}
        if text not in vals: return await update.message.reply_text("Выбери размер кнопкой ниже:",reply_markup=rect_kb())
        d["base_size"]=vals[text]; d["step"]="font" if d.get("source")=="text" else "heart"
        return await update.message.reply_text("Выбери шрифт:" if d["step"]=="font" else "Добавить сердечко?",reply_markup=font_kb() if d["step"]=="font" else heart_kb())
    if step=="font":
        vals={"Classic":"classic","Comic":"comic","GOST":"gost"}
        if text not in vals: return await update.message.reply_text("Выбери шрифт:",reply_markup=font_kb())
        d["font_choice"]=vals[text]; d["step"]="height"; return await update.message.reply_text("Выбери высоту текста:",reply_markup=height_kb())
    if step=="height":
        vals={f"{x} мм":float(x) for x in range(10,17)}
        if text not in vals: return await update.message.reply_text("Выбери высоту текста:",reply_markup=height_kb())
        d["text_size_mm"]=vals[text]; d["step"]="path"; return await update.message.reply_text("Выбери расположение текста:",reply_markup=path_kb())
    if step=="path":
        vals={"Обычный":"normal","Сверху":"top","Снизу":"bottom","По окружности":"full"}
        if text not in vals: return await update.message.reply_text("Выбери расположение:",reply_markup=path_kb())
        d["text_path"]=vals[text]; d["step"]="heart"; return await update.message.reply_text("Добавить сердечко?",reply_markup=heart_kb())
    if step=="heart":
        if text=="❤️ С сердцем": d["add_heart"]=True
        elif text=="Без сердца": d["add_heart"]=False
        else: return await update.message.reply_text("Добавить сердечко?",reply_markup=heart_kb())
        d["step"]="layout"; return await update.message.reply_text("Как расположить объекты в 3MF?",reply_markup=layout_kb())
    if step=="layout":
        if text=="✅ Собрать": d["layout_mode"]="assembled"
        elif text=="🧩 Отдельно": d["layout_mode"]="separate"
        else: return await update.message.reply_text("Выбери вариант:",reply_markup=layout_kb())
        d["step"]="create"; return await update.message.reply_text(stamp_summary(context),reply_markup=create_kb())
    if step=="create":
        if text!="🚀 СОЗДАТЬ 3MF": return await update.message.reply_text(stamp_summary(context),reply_markup=create_kb())
        d.pop("step",None); return await legacy.enqueue_job(update.message,context)
    return await stamp_menu(update,context)

async def callback_guard(update,context):
    # Old inline buttons can remain in chat history. They are intentionally disabled
    # so the active workflow has one reliable transport: reply-keyboard messages.
    await update.callback_query.answer("Используй нижнее меню",show_alert=False)

async def main_post_init(app):
    await legacy.post_init(app); await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")]); legacy.logger.info("CakeStampBot v1.9.0 reply-only stamp workflow started")
def main():
    app=Application.builder().token(legacy.BOT_TOKEN).post_init(main_post_init).post_shutdown(legacy.post_shutdown).build()
    app.add_handler(CommandHandler("start",guarded(start_v190))); app.add_handler(CommandHandler("help",guarded(help_v190))); app.add_handler(CommandHandler("stamp",guarded(stamp_menu))); app.add_handler(CommandHandler("topper",guarded(legacy.topper_cmd))); app.add_handler(CommandHandler("queue",guarded(legacy.queue_cmd))); app.add_handler(CommandHandler("users",users_cmd)); app.add_handler(CommandHandler("adduser",adduser_cmd)); app.add_handler(CommandHandler("deluser",deluser_cmd)); app.add_handler(CallbackQueryHandler(guarded(callback_guard))); app.add_handler(MessageHandler(filters.PHOTO,guarded(photo_router))); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,guarded(text_router))); app.add_error_handler(legacy.error_handler); app.run_polling()
if __name__=="__main__": main()
