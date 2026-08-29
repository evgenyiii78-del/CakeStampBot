import os
import sys
import uuid
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from engine import build_stamp_from_text, build_stamp_from_image, build_topper_from_text

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", stream=sys.stdout, force=True)
logger = logging.getLogger("CakeStampBot")
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Добавьте переменную окружения BOT_TOKEN.")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class CakeJob:
    chat_id: int
    params: dict[str, Any]

def main_menu_keyboard():
    return ReplyKeyboardMarkup([["🍰 Штамп", "🎂 Топпер"], ["📋 Очередь", "ℹ️ Помощь"]], resize_keyboard=True)
def mode_inline_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🍰 Штамп", callback_data="mode:stamp")], [InlineKeyboardButton("🎂 Топпер", callback_data="mode:topper")]])
def source_keyboard(mode):
    if mode == "topper": return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст", callback_data="source:text")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст", callback_data="source:text")], [InlineKeyboardButton("🖼 Картинка / логотип", callback_data="source:image")]])
def font_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Classic SL", callback_data="font:classic"), InlineKeyboardButton("Comic SL", callback_data="font:comic")], [InlineKeyboardButton("GOST SL", callback_data="font:gost")]])
def stamp_size_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("60 мм", callback_data="stamp_size:60"), InlineKeyboardButton("80 мм", callback_data="stamp_size:80")], [InlineKeyboardButton("105 мм", callback_data="stamp_size:105"), InlineKeyboardButton("130 мм", callback_data="stamp_size:130")], [InlineKeyboardButton("145 мм", callback_data="stamp_size:145")]])
def stamp_shape_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⭕ Круглая", callback_data="stamp_shape:round")], [InlineKeyboardButton("▭ Прямоугольная", callback_data="stamp_shape:rect")]])
def rect_size_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("80×60", callback_data="rect_size:80x60"), InlineKeyboardButton("100×70", callback_data="rect_size:100x70")], [InlineKeyboardButton("105×75", callback_data="rect_size:105x75"), InlineKeyboardButton("120×80", callback_data="rect_size:120x80")], [InlineKeyboardButton("145×95", callback_data="rect_size:145x95")]])
def stamp_text_path_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Обычный", callback_data="stamp_text_path:normal")], [InlineKeyboardButton("⌒ Сверху", callback_data="stamp_text_path:top"), InlineKeyboardButton("⌣ Снизу", callback_data="stamp_text_path:bottom")], [InlineKeyboardButton("⭕ По всей окружности", callback_data="stamp_text_path:full")]])
def stamp_text_size_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("5 мм", callback_data="stamp_text_size:5"), InlineKeyboardButton("6 мм", callback_data="stamp_text_size:6"), InlineKeyboardButton("7 мм", callback_data="stamp_text_size:7")], [InlineKeyboardButton("8 мм", callback_data="stamp_text_size:8"), InlineKeyboardButton("9 мм", callback_data="stamp_text_size:9"), InlineKeyboardButton("10 мм", callback_data="stamp_text_size:10")]])
def heart_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❤️ С сердцем", callback_data="heart:yes")], [InlineKeyboardButton("Без сердца", callback_data="heart:no")]])
def layout_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Собрать", callback_data="layout:assembled")], [InlineKeyboardButton("🧩 Отдельно", callback_data="layout:separate")]])
def topper_width_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("90 мм", callback_data="topper_width:90"), InlineKeyboardButton("120 мм", callback_data="topper_width:120")], [InlineKeyboardButton("150 мм", callback_data="topper_width:150"), InlineKeyboardButton("180 мм", callback_data="topper_width:180")]])
def topper_text_height_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("2.5 мм", callback_data="topper_text_h:2.5"), InlineKeyboardButton("3.0 мм", callback_data="topper_text_h:3.0")], [InlineKeyboardButton("3.5 мм", callback_data="topper_text_h:3.5"), InlineKeyboardButton("4.0 мм", callback_data="topper_text_h:4.0")]])
def topper_backing_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("0.8 мм", callback_data="topper_backing:0.8"), InlineKeyboardButton("1.2 мм", callback_data="topper_backing:1.2")], [InlineKeyboardButton("1.6 мм", callback_data="topper_backing:1.6"), InlineKeyboardButton("2.0 мм", callback_data="topper_backing:2.0")]])
def topper_legs_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Авто", callback_data="topper_legs:auto")], [InlineKeyboardButton("1 ножка", callback_data="topper_legs:one"), InlineKeyboardButton("2 ножки", callback_data="topper_legs:two")]])
def create_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Создать 3MF", callback_data="create")], [InlineKeyboardButton("🔁 Начать заново", callback_data="restart")]])

def ensure_topper_defaults(context):
    context.user_data.setdefault("mode", "topper")
    context.user_data.setdefault("source", "text")
    context.user_data.setdefault("font_choice", "classic")
    context.user_data.setdefault("topper_width", 120.0)
    context.user_data.setdefault("topper_text_height", 3.0)
    context.user_data.setdefault("topper_backing_height", 1.2)
    context.user_data.setdefault("topper_legs", "auto")
def stamp_font_name(context):
    c = str(context.user_data.get("font_choice", "classic")).lower()
    return {"classic":"Classic", "comic":"Comic Sans", "gost":"GOST"}.get(c, c or "Classic")
def stamp_summary_text(context):
    path = {"normal":"обычный", "top":"дугой сверху", "bottom":"дугой снизу", "full":"по окружности"}.get(context.user_data.get("text_path", "normal"), "обычный")
    return ("Проверь настройки штампа:\n\n"
            f"• источник: {'текст' if context.user_data.get('source') == 'text' else 'картинка'}\n"
            f"• размер: {str(context.user_data.get('base_size', '105')).replace('x','×')} мм\n"
            f"• форма: {'круглая' if context.user_data.get('base_shape') == 'round' else 'прямоугольная'}\n"
            f"• шрифт: {stamp_font_name(context)}\n"
            f"• высота текста: {context.user_data.get('text_size_mm', 7)} мм\n"
            f"• линия: {context.user_data.get('line_width', 0.25)} мм\n"
            f"• текст: {path}\n"
            f"• сердце: {'да' if context.user_data.get('add_heart') else 'нет'}\n"
            f"• раскладка: {'собрать' if context.user_data.get('layout_mode') == 'assembled' else 'отдельно'}")
def topper_summary_text(context):
    ensure_topper_defaults(context)
    lr = {"auto":"авто", "one":"1 ножка", "two":"2 ножки"}.get(context.user_data.get("topper_legs", "auto"), "авто")
    return f"Проверь настройки топпера:\n\n• ширина: {context.user_data.get('topper_width',120)} мм\n• высота текста: {context.user_data.get('topper_text_height',3.0)} мм\n• подложка под буквами: {context.user_data.get('topper_backing_height',1.2)} мм\n• ножки: {lr}"
async def send_or_edit_summary(q, context):
    await q.edit_message_text(stamp_summary_text(context) if context.user_data.get("mode") == "stamp" else topper_summary_text(context), reply_markup=create_keyboard())

async def start(update, context):
    context.user_data.clear()
    await update.message.reply_text("CakeStampBot v1.7.2", reply_markup=main_menu_keyboard())
    await update.message.reply_text("Выбери режим:", reply_markup=mode_inline_keyboard())
async def help_cmd(update, context):
    await update.message.reply_text("Помощь CakeStampBot v1.7.2\n\n🍰 Штамп: текст или картинка → PNG + 3MF.\n🎂 Топпер: текст → единая модель с подложкой и ножками.", reply_markup=main_menu_keyboard())
async def queue_cmd(update, context):
    q = context.application.bot_data.get("cake_queue")
    await update.message.reply_text(f"В очереди задач: {q.qsize() if q else 0}", reply_markup=main_menu_keyboard())
async def stamp_cmd(update, context):
    context.user_data.clear(); context.user_data["mode"] = "stamp"
    await update.message.reply_text("Режим: 🍰 Штамп. Выбери источник:", reply_markup=source_keyboard("stamp"))
async def topper_cmd(update, context):
    context.user_data.clear(); context.user_data.update(mode="topper", source="text")
    await update.message.reply_text("Режим: 🎂 Топпер. Напиши текст для топпера.")
async def on_text(update, context):
    text = update.message.text.strip()
    if text == "🍰 Штамп": return await stamp_cmd(update, context)
    if text == "🎂 Топпер": return await topper_cmd(update, context)
    if text == "📋 Очередь": return await queue_cmd(update, context)
    if text == "ℹ️ Помощь": return await help_cmd(update, context)
    mode = context.user_data.get("mode"); source = context.user_data.get("source")
    if not mode: return await update.message.reply_text("Сначала выбери режим:", reply_markup=mode_inline_keyboard())
    if source != "text": return await update.message.reply_text("Сначала выбери «Текст» или «Картинка».", reply_markup=source_keyboard(mode))
    context.user_data["text"] = text
    await update.message.reply_text("Выбери шрифт:", reply_markup=font_keyboard())
async def on_photo(update, context):
    if context.user_data.get("mode") != "stamp": return await update.message.reply_text("Картинки пока только в режиме 🍰 Штамп.")
    context.user_data["source"] = "image"
    f = await update.message.photo[-1].get_file(); p = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}.jpg"
    await f.download_to_drive(str(p)); context.user_data["image_path"] = str(p)
    await update.message.reply_text("Картинку получил. Выбери размер штампа:", reply_markup=stamp_size_keyboard())

async def on_callback(update, context):
    q = update.callback_query; await q.answer(); data = q.data or ""
    try:
        if data == "restart": context.user_data.clear(); return await q.edit_message_text("Начинаем заново. Выбери режим:", reply_markup=mode_inline_keyboard())
        if data.startswith("mode:"):
            mode=data.split(":",1)[1]; context.user_data.clear(); context.user_data["mode"]=mode
            if mode=="stamp": return await q.edit_message_text("Режим: 🍰 Штамп. Выбери источник:", reply_markup=source_keyboard("stamp"))
            context.user_data["source"]="text"; return await q.edit_message_text("Режим: 🎂 Топпер. Напиши текст для топпера.")
        if data.startswith("source:"):
            context.user_data["source"]=data.split(":",1)[1]; return await q.edit_message_text("Напиши текст." if context.user_data["source"]=="text" else "Пришли картинку или логотип.")
        if data.startswith("font:"):
            context.user_data["font_choice"]=data.split(":",1)[1]
            if context.user_data.get("mode")=="stamp": return await q.edit_message_text("Выбери размер штампа:", reply_markup=stamp_size_keyboard())
            ensure_topper_defaults(context); return await q.edit_message_text("Выбери ширину топпера:", reply_markup=topper_width_keyboard())
        if data.startswith("stamp_size:"): context.user_data["stamp_size"]=data.split(":",1)[1]; return await q.edit_message_text("Выбери форму подложки:", reply_markup=stamp_shape_keyboard())
        if data.startswith("stamp_shape:"):
            shape=data.split(":",1)[1]; context.user_data["base_shape"]=shape
            if shape=="rect": return await q.edit_message_text("Выбери размер прямоугольной подложки:", reply_markup=rect_size_keyboard())
            context.user_data["base_size"]=context.user_data.get("stamp_size","105"); context.user_data["line_width"]=0.25
            if context.user_data.get("source")=="text": return await q.edit_message_text("Как расположить текст?", reply_markup=stamp_text_path_keyboard())
            context.user_data["text_path"]="normal"; return await q.edit_message_text("Добавить сердечко?", reply_markup=heart_keyboard())
        if data.startswith("rect_size:"):
            context.user_data["base_size"]=data.split(":",1)[1]; context.user_data["line_width"]=0.25; context.user_data["text_path"]="normal"
            if context.user_data.get("source")=="text": return await q.edit_message_text("Выбери высоту текста:", reply_markup=stamp_text_size_keyboard())
            return await q.edit_message_text("Добавить сердечко?", reply_markup=heart_keyboard())
        if data.startswith("stamp_text_path:"):
            context.user_data["text_path"]=data.split(":",1)[1]
            return await q.edit_message_text("Выбери высоту текста:", reply_markup=stamp_text_size_keyboard())
        if data.startswith("stamp_text_size:"):
            context.user_data["text_size_mm"]=float(data.split(":",1)[1])
            return await q.edit_message_text("Добавить сердечко?", reply_markup=heart_keyboard())
        if data.startswith("heart:"): context.user_data["add_heart"]=data.split(":",1)[1]=="yes"; return await q.edit_message_text("Как расположить объекты в 3MF?", reply_markup=layout_keyboard())
        if data.startswith("layout:"): context.user_data["layout_mode"]=data.split(":",1)[1]; return await send_or_edit_summary(q, context)
        if data.startswith("topper_width:"): ensure_topper_defaults(context); context.user_data["topper_width"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери высоту текста:", reply_markup=topper_text_height_keyboard())
        if data.startswith("topper_text_h:"): context.user_data["topper_text_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери толщину подложки под буквами:", reply_markup=topper_backing_keyboard())
        if data.startswith("topper_backing:"): context.user_data["topper_backing_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Сколько ножек сделать?", reply_markup=topper_legs_keyboard())
        if data.startswith("topper_legs:") or data.startswith("topper_leg:") or data.startswith("legs:"): context.user_data["topper_legs"]=data.split(":",1)[1]; return await send_or_edit_summary(q, context)
        if data=="create": return await enqueue_job(q.message, context)
    except Exception:
        logger.exception("Callback processing failed | data=%s", data); await q.message.reply_text("Кнопка не обработалась из-за ошибки. Попробуй /start.")

async def enqueue_job(message, context):
    q=context.application.bot_data["cake_queue"]
    if context.user_data.get("mode")=="topper": ensure_topper_defaults(context)
    params=dict(context.user_data)
    if params.get("mode")=="topper" and not params.get("text"): return await message.reply_text("Я потерял текст топпера. Напиши текст ещё раз.")
    if params.get("mode")=="stamp" and params.get("source")=="text" and not params.get("text"): return await message.reply_text("Я потерял текст штампа. Напиши текст ещё раз.")
    await q.put(CakeJob(message.chat_id,params)); await message.reply_text(f"✅ Задача добавлена в очередь.\n\nПозиция: {q.qsize()}\nСоздание 3MF может занять 30–120 секунд.", reply_markup=main_menu_keyboard()); context.user_data.clear()
def build_model(params):
    out=OUTPUT_DIR/uuid.uuid4().hex[:10]
    if params.get("mode")=="topper": return build_topper_from_text(text=params["text"], output_dir=str(out), width_mm=float(params.get("topper_width",120)), font_choice=params.get("font_choice","classic"), text_height=float(params.get("topper_text_height",3.0)), backing_height=float(params.get("topper_backing_height",1.2)), legs=params.get("topper_legs","auto"))
    if params.get("source")=="image": return build_stamp_from_image(image_path=params["image_path"], output_dir=str(out), base_size=params.get("base_size","105"), base_shape=params.get("base_shape","round"), line_width=0.25, add_heart=bool(params.get("add_heart",False)), layout_mode=params.get("layout_mode","assembled"))
    return build_stamp_from_text(text=params["text"], output_dir=str(out), base_size=params.get("base_size","105"), base_shape=params.get("base_shape","round"), line_width=0.25, font_choice=params.get("font_choice","classic"), text_path=params.get("text_path","normal"), text_size_mm=float(params.get("text_size_mm",7.0)), add_heart=bool(params.get("add_heart",False)), layout_mode=params.get("layout_mode","assembled"))
async def cake_worker(app):
    q=app.bot_data["cake_queue"]
    while True:
        job=await q.get()
        try:
            await app.bot.send_message(chat_id=job.chat_id,text="🔧 Начал обработку модели...\nВекторная обработка может занять 30–120 секунд.")
            result=await asyncio.wait_for(asyncio.to_thread(build_model,job.params),timeout=210)
            with open(result.preview_png,"rb") as f: await app.bot.send_photo(chat_id=job.chat_id,photo=f,caption="Превью проекта.")
            with open(result.project_3mf,"rb") as f: await app.bot.send_document(chat_id=job.chat_id,document=f,filename=Path(result.project_3mf).name,caption="Готово ✅ Это 3MF-проект.",reply_markup=main_menu_keyboard())
        except Exception as exc:
            logger.exception("MODEL BUILD FAILED"); await app.bot.send_message(chat_id=job.chat_id,text=f"Не получилось собрать модель.\n\nОшибка: {exc}")
        finally: q.task_done()
async def post_init(app):
    app.bot_data["cake_queue"]=asyncio.Queue(); app.bot_data["cake_worker_task"]=asyncio.create_task(cake_worker(app)); await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")])
async def post_shutdown(app):
    t=app.bot_data.get("cake_worker_task")
    if t: t.cancel()
async def error_handler(update,context): logger.exception("Unhandled error",exc_info=context.error)
def main():
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("help",help_cmd)); app.add_handler(CommandHandler("stamp",stamp_cmd)); app.add_handler(CommandHandler("topper",topper_cmd)); app.add_handler(CommandHandler("queue",queue_cmd)); app.add_handler(CallbackQueryHandler(on_callback)); app.add_handler(MessageHandler(filters.PHOTO,on_photo)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,on_text)); app.add_error_handler(error_handler)
    logger.info("CakeStampBot v1.7.2 started"); app.run_polling()
if __name__=="__main__": main()
