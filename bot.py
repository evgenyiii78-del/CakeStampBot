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
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN не задан. Добавьте переменную окружения BOT_TOKEN.")
DATA_DIR=Path(os.getenv("DATA_DIR","data")); UPLOAD_DIR=DATA_DIR/"uploads"; OUTPUT_DIR=DATA_DIR/"outputs"
UPLOAD_DIR.mkdir(parents=True,exist_ok=True); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)

@dataclass
class CakeJob:
    chat_id:int
    params:dict[str,Any]

def main_menu_keyboard(): return ReplyKeyboardMarkup([["🍰 Штамп","🎂 Топпер"],["📋 Очередь","ℹ️ Помощь"]],resize_keyboard=True)
def mode_inline_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("🍰 Штамп",callback_data="mode:stamp")],[InlineKeyboardButton("🎂 Топпер",callback_data="mode:topper")]])
def source_keyboard(mode):
    if mode=="topper": return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст",callback_data="source:text")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст",callback_data="source:text")],[InlineKeyboardButton("🖼 Картинка / логотип",callback_data="source:image")]])
def font_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("Classic SL",callback_data="font:classic"),InlineKeyboardButton("Comic SL",callback_data="font:comic")],[InlineKeyboardButton("GOST SL",callback_data="font:gost")]])
def stamp_size_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("60 мм",callback_data="stamp_size:60"),InlineKeyboardButton("80 мм",callback_data="stamp_size:80")],[InlineKeyboardButton("105 мм",callback_data="stamp_size:105"),InlineKeyboardButton("130 мм",callback_data="stamp_size:130")],[InlineKeyboardButton("145 мм",callback_data="stamp_size:145")]])
def stamp_shape_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("⭕ Круглая",callback_data="stamp_shape:round")],[InlineKeyboardButton("▭ Прямоугольная",callback_data="stamp_shape:rect")]])
def rect_size_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("80×60",callback_data="rect_size:80x60"),InlineKeyboardButton("100×70",callback_data="rect_size:100x70")],[InlineKeyboardButton("105×75",callback_data="rect_size:105x75"),InlineKeyboardButton("120×80",callback_data="rect_size:120x80")],[InlineKeyboardButton("145×95",callback_data="rect_size:145x95")]])
def topper_width_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("90 мм",callback_data="topper_width:90"),InlineKeyboardButton("120 мм",callback_data="topper_width:120")],[InlineKeyboardButton("150 мм",callback_data="topper_width:150"),InlineKeyboardButton("180 мм",callback_data="topper_width:180")]])
def topper_text_height_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("2.5 мм",callback_data="topper_text_h:2.5"),InlineKeyboardButton("3.0 мм",callback_data="topper_text_h:3.0")],[InlineKeyboardButton("3.5 мм",callback_data="topper_text_h:3.5"),InlineKeyboardButton("4.0 мм",callback_data="topper_text_h:4.0")]])
def topper_backing_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("0.8 мм",callback_data="topper_backing:0.8"),InlineKeyboardButton("1.2 мм",callback_data="topper_backing:1.2")],[InlineKeyboardButton("1.6 мм",callback_data="topper_backing:1.6"),InlineKeyboardButton("2.0 мм",callback_data="topper_backing:2.0")]])
def topper_legs_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("Авто",callback_data="topper_legs:auto")],[InlineKeyboardButton("1 ножка",callback_data="topper_legs:one"),InlineKeyboardButton("2 ножки",callback_data="topper_legs:two")]])
def create_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Создать 3MF",callback_data="create")],[InlineKeyboardButton("🔁 Начать заново",callback_data="restart")]])

def ensure_topper_defaults(c):
    c.user_data.setdefault("mode","topper"); c.user_data.setdefault("source","text"); c.user_data.setdefault("font_choice","classic"); c.user_data.setdefault("topper_width",120.0); c.user_data.setdefault("topper_text_height",3.0); c.user_data.setdefault("topper_backing_height",1.2); c.user_data.setdefault("topper_legs","auto")
def ensure_stamp_defaults(c):
    d=c.user_data; d.setdefault("mode","stamp"); d.setdefault("source","text"); d.setdefault("base_shape","round"); d.setdefault("base_size","105"); d.setdefault("stamp_size","105"); d.setdefault("font_choice","classic"); d.setdefault("text_size_mm",7.0); d.setdefault("text_path","normal"); d.setdefault("line_width",0.25); d.setdefault("add_heart",False); d.setdefault("layout_mode","separate")
def mark(label,active): return ("✓ "+label) if active else label
def stamp_font_name(c):
    x=str(c.user_data.get("font_choice","classic")).lower(); return {"classic":"Classic","comic":"Comic Sans","gost":"GOST"}.get(x,x)
def stamp_settings_text(c):
    ensure_stamp_defaults(c); d=c.user_data; path={"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d["text_path"],"Обычный")
    return ("🍰 НАСТРОЙКИ ШТАМПА\n\n"+f"📝 Текст: {d.get('text','')}\n\n"+f"🔵 Диаметр: {d['base_size']} мм\n"+f"🔤 Шрифт: {stamp_font_name(c)}\n"+f"↕️ Высота текста: {d['text_size_mm']:g} мм\n"+f"〰️ Расположение: {path}\n"+"✏️ Толщина линии: 0.25 мм\n"+f"❤️ Сердце: {'Да' if d['add_heart'] else 'Нет'}\n"+f"🧩 3MF: {'Собрать' if d['layout_mode']=='assembled' else 'Отдельно'}")
def stamp_quick_keyboard(c):
    ensure_stamp_defaults(c); d=c.user_data; size=str(d["base_size"]); path=d["text_path"]; fs=d["font_choice"]; h=float(d["text_size_mm"])
    return InlineKeyboardMarkup([
      [InlineKeyboardButton(mark("60",size=="60"),callback_data="qs:size:60"),InlineKeyboardButton(mark("80",size=="80"),callback_data="qs:size:80"),InlineKeyboardButton(mark("105",size=="105"),callback_data="qs:size:105")],
      [InlineKeyboardButton(mark("130",size=="130"),callback_data="qs:size:130"),InlineKeyboardButton(mark("145",size=="145"),callback_data="qs:size:145")],
      [InlineKeyboardButton(mark("Обычный",path=="normal"),callback_data="qs:path:normal"),InlineKeyboardButton(mark("Сверху",path=="top"),callback_data="qs:path:top")],
      [InlineKeyboardButton(mark("Снизу",path=="bottom"),callback_data="qs:path:bottom"),InlineKeyboardButton(mark("По окружности",path=="full"),callback_data="qs:path:full")],
      [InlineKeyboardButton(mark("5 мм",h==5),callback_data="qs:h:5"),InlineKeyboardButton(mark("6 мм",h==6),callback_data="qs:h:6"),InlineKeyboardButton(mark("7 мм",h==7),callback_data="qs:h:7")],
      [InlineKeyboardButton(mark("8 мм",h==8),callback_data="qs:h:8"),InlineKeyboardButton(mark("9 мм",h==9),callback_data="qs:h:9"),InlineKeyboardButton(mark("10 мм",h==10),callback_data="qs:h:10")],
      [InlineKeyboardButton(mark("Classic",fs=="classic"),callback_data="qs:font:classic"),InlineKeyboardButton(mark("Comic",fs=="comic"),callback_data="qs:font:comic"),InlineKeyboardButton(mark("GOST",fs=="gost"),callback_data="qs:font:gost")],
      [InlineKeyboardButton(mark("❤️ Сердце",d["add_heart"]),callback_data="qs:heart"),InlineKeyboardButton(mark("🧩 Отдельно",d["layout_mode"]=="separate"),callback_data="qs:layout")],
      [InlineKeyboardButton("🚀 СОЗДАТЬ 3MF",callback_data="create")],
      [InlineKeyboardButton("↩️ Назад в меню",callback_data="restart")]
    ])
async def show_stamp_settings(target,c):
    text=stamp_settings_text(c); kb=stamp_quick_keyboard(c)
    if hasattr(target,"edit_message_text"): await target.edit_message_text(text,reply_markup=kb)
    else: await target.reply_text(text,reply_markup=kb)
def topper_summary_text(c):
    ensure_topper_defaults(c); lr={"auto":"авто","one":"1 ножка","two":"2 ножки"}.get(c.user_data.get("topper_legs","auto"),"авто")
    return f"Проверь настройки топпера:\n\n• ширина: {c.user_data.get('topper_width',120)} мм\n• высота текста: {c.user_data.get('topper_text_height',3.0)} мм\n• подложка под буквами: {c.user_data.get('topper_backing_height',1.2)} мм\n• ножки: {lr}"

async def start(u,c): c.user_data.clear(); await u.message.reply_text("CakeStampBot v1.8.0",reply_markup=main_menu_keyboard()); await u.message.reply_text("Выбери режим:",reply_markup=mode_inline_keyboard())
async def help_cmd(u,c): await u.message.reply_text("Помощь CakeStampBot v1.8.0\n\n🍰 Штамп: после текста все параметры доступны на одном экране.\n🎂 Топпер: текст → единая модель с подложкой и ножками.",reply_markup=main_menu_keyboard())
async def queue_cmd(u,c):
    q=c.application.bot_data.get("cake_queue"); await u.message.reply_text(f"В очереди задач: {q.qsize() if q else 0}",reply_markup=main_menu_keyboard())
async def stamp_cmd(u,c): c.user_data.clear(); c.user_data["mode"]="stamp"; await u.message.reply_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_keyboard("stamp"))
async def topper_cmd(u,c): c.user_data.clear(); c.user_data.update(mode="topper",source="text"); await u.message.reply_text("Режим: 🎂 Топпер. Напиши текст для топпера.")
async def on_text(u,c):
    text=u.message.text.strip()
    if text=="🍰 Штамп": return await stamp_cmd(u,c)
    if text=="🎂 Топпер": return await topper_cmd(u,c)
    if text=="📋 Очередь": return await queue_cmd(u,c)
    if text=="ℹ️ Помощь": return await help_cmd(u,c)
    mode=c.user_data.get("mode"); source=c.user_data.get("source")
    if not mode: return await u.message.reply_text("Сначала выбери режим:",reply_markup=mode_inline_keyboard())
    if source!="text": return await u.message.reply_text("Сначала выбери «Текст» или «Картинка».",reply_markup=source_keyboard(mode))
    c.user_data["text"]=text
    if mode=="stamp": ensure_stamp_defaults(c); return await show_stamp_settings(u.message,c)
    return await u.message.reply_text("Выбери шрифт:",reply_markup=font_keyboard())
async def on_photo(u,c):
    if c.user_data.get("mode")!="stamp": return await u.message.reply_text("Картинки пока только в режиме 🍰 Штамп.")
    c.user_data["source"]="image"; f=await u.message.photo[-1].get_file(); p=UPLOAD_DIR/f"{uuid.uuid4().hex[:10]}.jpg"; await f.download_to_drive(str(p)); c.user_data["image_path"]=str(p); await u.message.reply_text("Картинку получил. Выбери размер штампа:",reply_markup=stamp_size_keyboard())

async def on_callback(u,c):
    q=u.callback_query; await q.answer(); data=q.data or ""
    try:
      if data=="restart": c.user_data.clear(); return await q.edit_message_text("Начинаем заново. Выбери режим:",reply_markup=mode_inline_keyboard())
      if data.startswith("qs:"):
        ensure_stamp_defaults(c); p=data.split(":")
        if p[1]=="size": c.user_data["base_size"]=p[2]; c.user_data["stamp_size"]=p[2]
        elif p[1]=="path": c.user_data["text_path"]=p[2]
        elif p[1]=="h": c.user_data["text_size_mm"]=float(p[2])
        elif p[1]=="font": c.user_data["font_choice"]=p[2]
        elif p[1]=="heart": c.user_data["add_heart"]=not bool(c.user_data.get("add_heart"))
        elif p[1]=="layout": c.user_data["layout_mode"]="assembled" if c.user_data.get("layout_mode")=="separate" else "separate"
        return await show_stamp_settings(q,c)
      if data.startswith("mode:"):
        mode=data.split(":",1)[1]; c.user_data.clear(); c.user_data["mode"]=mode
        if mode=="stamp": return await q.edit_message_text("Режим: 🍰 Штамп. Выбери источник:",reply_markup=source_keyboard("stamp"))
        c.user_data["source"]="text"; return await q.edit_message_text("Режим: 🎂 Топпер. Напиши текст для топпера.")
      if data.startswith("source:"): c.user_data["source"]=data.split(":",1)[1]; return await q.edit_message_text("Напиши текст." if c.user_data["source"]=="text" else "Пришли картинку или логотип.")
      if data.startswith("font:"):
        c.user_data["font_choice"]=data.split(":",1)[1]
        if c.user_data.get("mode")=="stamp": ensure_stamp_defaults(c); return await show_stamp_settings(q,c)
        ensure_topper_defaults(c); return await q.edit_message_text("Выбери ширину топпера:",reply_markup=topper_width_keyboard())
      if data.startswith("stamp_size:"): c.user_data["stamp_size"]=data.split(":",1)[1]; return await q.edit_message_text("Выбери форму подложки:",reply_markup=stamp_shape_keyboard())
      if data.startswith("stamp_shape:"):
        shape=data.split(":",1)[1]; c.user_data["base_shape"]=shape
        if shape=="rect": return await q.edit_message_text("Выбери размер прямоугольной подложки:",reply_markup=rect_size_keyboard())
        c.user_data["base_size"]=c.user_data.get("stamp_size","105"); c.user_data["line_width"]=0.25; c.user_data["text_path"]="normal"; c.user_data["add_heart"]=False; c.user_data["layout_mode"]="separate"
        if c.user_data.get("source")=="text": ensure_stamp_defaults(c); return await show_stamp_settings(q,c)
        return await q.edit_message_text("Добавить сердечко?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❤️ С сердцем",callback_data="heart:yes")],[InlineKeyboardButton("Без сердца",callback_data="heart:no")]]))
      if data.startswith("rect_size:"): c.user_data["base_size"]=data.split(":",1)[1]; c.user_data["line_width"]=0.25; c.user_data["text_path"]="normal"; c.user_data["add_heart"]=False; c.user_data["layout_mode"]="separate"; return await q.edit_message_text("Добавить сердечко?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❤️ С сердцем",callback_data="heart:yes")],[InlineKeyboardButton("Без сердца",callback_data="heart:no")]]))
      if data.startswith("heart:"): c.user_data["add_heart"]=data.split(":",1)[1]=="yes"; return await q.edit_message_text("Как расположить объекты в 3MF?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Собрать",callback_data="layout:assembled")],[InlineKeyboardButton("🧩 Отдельно",callback_data="layout:separate")]]))
      if data.startswith("layout:"): c.user_data["layout_mode"]=data.split(":",1)[1]; return await q.edit_message_text("Проверь настройки и создай 3MF.",reply_markup=create_keyboard())
      if data.startswith("topper_width:"): ensure_topper_defaults(c); c.user_data["topper_width"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери высоту текста:",reply_markup=topper_text_height_keyboard())
      if data.startswith("topper_text_h:"): c.user_data["topper_text_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Выбери толщину подложки под буквами:",reply_markup=topper_backing_keyboard())
      if data.startswith("topper_backing:"): c.user_data["topper_backing_height"]=float(data.split(":",1)[1]); return await q.edit_message_text("Сколько ножек сделать?",reply_markup=topper_legs_keyboard())
      if data.startswith("topper_legs:"): c.user_data["topper_legs"]=data.split(":",1)[1]; return await q.edit_message_text(topper_summary_text(c),reply_markup=create_keyboard())
      if data=="create": return await enqueue_job(q.message,c)
    except Exception:
      logger.exception("Callback failed %s",data); await q.message.reply_text("Ошибка обработки кнопки. Попробуй /start.")

async def enqueue_job(message,c):
    qq=c.application.bot_data["cake_queue"]
    if c.user_data.get("mode")=="topper": ensure_topper_defaults(c)
    params=dict(c.user_data)
    if not params.get("text") and params.get("source")=="text": return await message.reply_text("Я потерял текст. Напиши его ещё раз.")
    await qq.put(CakeJob(message.chat_id,params)); await message.reply_text(f"✅ Задача добавлена в очередь.\n\nПозиция: {qq.qsize()}\nСоздание 3MF может занять 30–120 секунд.",reply_markup=main_menu_keyboard()); c.user_data.clear()
def build_model(p):
    out=OUTPUT_DIR/uuid.uuid4().hex[:10]
    if p.get("mode")=="topper": return build_topper_from_text(text=p["text"],output_dir=str(out),width_mm=float(p.get("topper_width",120)),font_choice=p.get("font_choice","classic"),text_height=float(p.get("topper_text_height",3.0)),backing_height=float(p.get("topper_backing_height",1.2)),legs=p.get("topper_legs","auto"))
    if p.get("source")=="image": return build_stamp_from_image(image_path=p["image_path"],output_dir=str(out),base_size=p.get("base_size","105"),base_shape=p.get("base_shape","round"),line_width=0.25,add_heart=bool(p.get("add_heart",False)),layout_mode=p.get("layout_mode","assembled"))
    return build_stamp_from_text(text=p["text"],output_dir=str(out),base_size=p.get("base_size","105"),base_shape=p.get("base_shape","round"),line_width=0.25,font_choice=p.get("font_choice","classic"),text_path=p.get("text_path","normal"),text_size_mm=float(p.get("text_size_mm",7)),add_heart=bool(p.get("add_heart",False)),layout_mode=p.get("layout_mode","separate"))
async def cake_worker(app):
    qq=app.bot_data["cake_queue"]
    while True:
      job=await qq.get()
      try:
        await app.bot.send_message(chat_id=job.chat_id,text="🔧 Начал обработку модели...\nВекторная обработка может занять 30–120 секунд."); result=await asyncio.wait_for(asyncio.to_thread(build_model,job.params),timeout=210)
        with open(result.preview_png,"rb") as f: await app.bot.send_photo(chat_id=job.chat_id,photo=f,caption="Превью проекта.")
        with open(result.project_3mf,"rb") as f: await app.bot.send_document(chat_id=job.chat_id,document=f,filename=Path(result.project_3mf).name,caption="Готово ✅ Это 3MF-проект.",reply_markup=main_menu_keyboard())
      except Exception as exc: logger.exception("MODEL BUILD FAILED"); await app.bot.send_message(chat_id=job.chat_id,text=f"Не получилось собрать модель.\n\nОшибка: {exc}")
      finally: qq.task_done()
async def post_init(app): app.bot_data["cake_queue"]=asyncio.Queue(); app.bot_data["cake_worker_task"]=asyncio.create_task(cake_worker(app)); await app.bot.set_my_commands([("start","Главное меню"),("stamp","Штамп"),("topper","Топпер"),("queue","Очередь"),("help","Помощь")])
async def post_shutdown(app):
    t=app.bot_data.get("cake_worker_task")
    if t: t.cancel()
async def error_handler(u,c): logger.exception("Unhandled error",exc_info=c.error)
def main():
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build(); app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("help",help_cmd)); app.add_handler(CommandHandler("stamp",stamp_cmd)); app.add_handler(CommandHandler("topper",topper_cmd)); app.add_handler(CommandHandler("queue",queue_cmd)); app.add_handler(CallbackQueryHandler(on_callback)); app.add_handler(MessageHandler(filters.PHOTO,on_photo)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,on_text)); app.add_error_handler(error_handler); logger.info("CakeStampBot v1.8.0 started"); app.run_polling()
if __name__=="__main__": main()
