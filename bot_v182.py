"""CakeStampBot v1.8.9 Reply-keyboard workflow + Access Control.
Main mode and stamp source selection use Telegram reply keyboards.
Stamp/topper geometry untouched.
"""
import os
import json
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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
        if update.callback_query.message: await update.callback_query.message.reply_text(text)
    elif update.effective_message: await update.effective_message.reply_text(text)
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
    ids=_load_allowed(); ids.discard(target); _save_allowed(ids)
    if target in ENV_ALLOWED_IDS: return await update.effective_message.reply_text(f"⚠️ {target} остаётся разрешён через ALLOWED_USER_IDS в окружении.")
    await update.effective_message.reply_text(f"🚫 Доступ закрыт: {target}")

def source_reply_keyboard():
    return ReplyKeyboardMarkup([["✍️ Текст","🖼 Картинка / логотип"],["↩️ Главное меню"]],resize_keyboard=True)

def _ensure_defaults(c):
    legacy.ensure_stamp_defaults(c); h=float(c.user_data.get("text_size_mm",12))
    if h<10 or h>16: c.user_data["text_size_mm"]=12.0
def compact_keyboard(c):
    _ensure_defaults(c); d=c.user_data; path={"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d.get("text_path"),"Обычный")
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"🔵 Диаметр · {d.get('base_size','105')} мм",callback_data="qcat:size"),InlineKeyboardButton(f"🔤 Шрифт · {legacy.stamp_font_name(c)}",callback_data="qcat:font")],[InlineKeyboardButton(f"↕️ Размер · {float(d.get('text_size_mm',12)):g} мм",callback_data="qcat:h"),InlineKeyboardButton(f"〰️ {path}",callback_data="qcat:path")],[InlineKeyboardButton(f"❤️ Сердце · {'Да' if d.get('add_heart') else 'Нет'}",callback_data="qs:heart"),InlineKeyboardButton(f"🧩 3MF · {'Собрать' if d.get('layout_mode')=='assembled' else 'Отдельно'}",callback_data="qs:layout")],[InlineKeyboardButton("🚀 СОЗДАТЬ 3MF",callback_data="create")],[InlineKeyboardButton("↩️ Назад в меню",callback_data="restart")]])
def category_keyboard(c,kind):
    _ensure_defaults(c); d=c.user_data; back=[InlineKeyboardButton("↩️ К настройкам",callback_data="qcat:back")]
    if kind=="size":
        cur=str(d.get("base_size","105")); vals=["60","80","105","130","145"]; return InlineKeyboardMarkup([[InlineKeyboardButton(("✓ " if cur==v else "")+v+" мм",callback_data=f"qs:size:{v}") for v in vals[:3]],[InlineKeyboardButton(("✓ " if cur==v else "")+v+" мм",callback_data=f"qs:size:{v}") for v in vals[3:]],back])
    if kind=="h":
        cur=float(d.get("text_size_mm",12)); vals=[10,11,12,13,14,15,16]; return InlineKeyboardMarkup([[InlineKeyboardButton(("✓ " if cur==v else "")+f"{v} мм",callback_data=f"qs:h:{v}") for v in vals[:4]],[InlineKeyboardButton(("✓ " if cur==v else "")+f"{v} мм",callback_data=f"qs:h:{v}") for v in vals[4:]],back])
    if kind=="font":
        cur=d.get("font_choice","classic"); vals=[("classic","Classic"),("comic","Comic"),("gost","GOST")]; return InlineKeyboardMarkup([[InlineKeyboardButton(("✓ " if cur==v else "")+name,callback_data=f"qs:font:{v}") for v,name in vals],back])
    cur=d.get("text_path","normal"); vals=[("normal","Обычный"),("top","Сверху"),("bottom","Снизу"),("full","По окружности")]; return InlineKeyboardMarkup([[InlineKeyboardButton(("✓ " if cur==v else "")+name,callback_data=f"qs:path:{v}") for v,name in vals[:2]],[InlineKeyboardButton(("✓ " if cur==v else "")+name,callback_data=f"qs:path:{v}") for v,name in vals[2:]],back])
legacy.stamp_quick_keyboard=compact_keyboard
_original_callback=legacy.on_callback
async def compact_callback(update,context):
    q=update.callback_query; data=q.data or ""
    if data.startswith("qcat:"):
        await q.answer(); kind=data.split(":",1)[1]
        if kind=="back": return await legacy.show_stamp_settings(q,context)
        titles={"size":"🔵 Выберите диаметр","font":"🔤 Выберите шрифт","h":"↕️ Выберите высоту текста 10–16 мм","path":"〰️ Выберите расположение текста"}; return await q.edit_message_text(titles.get(kind,"Настройка"),reply_markup=category_keyboard(context,kind))
    return await _original_callback(update,context)
legacy.on_callback=compact_callback

async def start_v189(update,context):
    context.user_data.clear(); await update.message.reply_text("CakeStampBot v1.8.9\n\nВыбери действие в меню ниже 👇",reply_markup=legacy.main_menu_keyboard())
async def help_v189(update,context):
    await update.message.reply_text("Помощь CakeStampBot v1.8.9\n\n🍰 Штамп → ✍️ Текст или 🖼 Картинка / логотип.\n↕️ Высота текста: 10–16 мм.\n📐 Отступ от края: около 20 мм.\n✏️ Линия: 0.25 мм.\n🔒 Доступ только для разрешённых Telegram ID.\n🎂 Топпер: без изменений.",reply_markup=legacy.main_menu_keyboard())
async def stamp_menu(update,context):
    context.user_data.clear(); context.user_data["mode"]="stamp"
    await update.message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_reply_keyboard())
async def text_router(update,context):
    text=(update.message.text or "").strip()
    if text=="ℹ️ Помощь": return await help_v189(update,context)
    if text=="🍰 Штамп": return await stamp_menu(update,context)
    if text=="🎂 Топпер": return await legacy.topper_cmd(update,context)
    if text=="📋 Очередь": return await legacy.queue_cmd(update,context)
    if text=="↩️ Главное меню":
        context.user_data.clear(); return await update.message.reply_text("Главное меню:",reply_markup=legacy.main_menu_keyboard())
    if context.user_data.get("mode")=="stamp" and text=="✍️ Текст":
        context.user_data["source"]="text"; return await update.message.reply_text("Напиши текст штампа:",reply_markup=source_reply_keyboard())
    if context.user_data.get("mode")=="stamp" and text=="🖼 Картинка / логотип":
        context.user_data["source"]="image"; return await update.message.reply_text("Пришли картинку или логотип:",reply_markup=source_reply_keyboard())
    return await legacy.on_text(update,context)

async def main_post_init(app):
    await legacy.post_init(app); await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")]); legacy.logger.info("CakeStampBot v1.8.9 Access Control started; admins=%s",sorted(ADMIN_IDS))
def main():
    app=Application.builder().token(legacy.BOT_TOKEN).post_init(main_post_init).post_shutdown(legacy.post_shutdown).build()
    app.add_handler(CommandHandler("start",guarded(start_v189))); app.add_handler(CommandHandler("help",guarded(help_v189))); app.add_handler(CommandHandler("stamp",guarded(stamp_menu))); app.add_handler(CommandHandler("topper",guarded(legacy.topper_cmd))); app.add_handler(CommandHandler("queue",guarded(legacy.queue_cmd))); app.add_handler(CommandHandler("users",users_cmd)); app.add_handler(CommandHandler("adduser",adduser_cmd)); app.add_handler(CommandHandler("deluser",deluser_cmd)); app.add_handler(CallbackQueryHandler(guarded(compact_callback))); app.add_handler(MessageHandler(filters.PHOTO,guarded(legacy.on_photo))); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,guarded(text_router))); app.add_error_handler(legacy.error_handler); app.run_polling()
if __name__=="__main__": main()
