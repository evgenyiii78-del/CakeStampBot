import os, sys, uuid, asyncio, logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from engine import build_stamp_from_text, build_stamp_from_image, build_topper_from_text
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s', stream=sys.stdout, force=True)
logger=logging.getLogger('CakeStampBot')
BOT_TOKEN=os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN не задан. Добавьте переменную окружения BOT_TOKEN.')
DATA_DIR=Path(os.getenv('DATA_DIR','data')); UPLOAD_DIR=DATA_DIR/'uploads'; OUTPUT_DIR=DATA_DIR/'outputs'; UPLOAD_DIR.mkdir(parents=True,exist_ok=True); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
@dataclass
class CakeJob: chat_id:int; params:dict[str,Any]

def main_menu_keyboard(): return ReplyKeyboardMarkup([['🍰 Штамп','🎂 Топпер'],['📋 Очередь','ℹ️ Помощь']],resize_keyboard=True)
def mode_inline_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('🍰 Штамп',callback_data='mode:stamp')],[InlineKeyboardButton('🎂 Топпер',callback_data='mode:topper')]])
def source_keyboard(mode): return InlineKeyboardMarkup([[InlineKeyboardButton('✍️ Текст',callback_data='source:text')]] if mode=='topper' else [[InlineKeyboardButton('✍️ Текст',callback_data='source:text')],[InlineKeyboardButton('🖼 Картинка / логотип',callback_data='source:image')]])
def font_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('Classic',callback_data='font:classic'),InlineKeyboardButton('Comic',callback_data='font:comic')],[InlineKeyboardButton('GOST',callback_data='font:gost')]])
def stamp_size_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('60 мм',callback_data='stamp_size:60'),InlineKeyboardButton('80 мм',callback_data='stamp_size:80')],[InlineKeyboardButton('105 мм',callback_data='stamp_size:105'),InlineKeyboardButton('145 мм',callback_data='stamp_size:145')]])
def stamp_shape_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('⭕ Круглая',callback_data='stamp_shape:round')],[InlineKeyboardButton('▭ Прямоугольная',callback_data='stamp_shape:rect')]])
def rect_size_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('80×60',callback_data='rect_size:80x60'),InlineKeyboardButton('100×70',callback_data='rect_size:100x70')],[InlineKeyboardButton('105×75',callback_data='rect_size:105x75'),InlineKeyboardButton('120×80',callback_data='rect_size:120x80')],[InlineKeyboardButton('145×95',callback_data='rect_size:145x95')]])
def stamp_width_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('0.35',callback_data='stamp_width:0.35'),InlineKeyboardButton('0.45',callback_data='stamp_width:0.45')],[InlineKeyboardButton('0.60',callback_data='stamp_width:0.60'),InlineKeyboardButton('0.80',callback_data='stamp_width:0.80')]])
def heart_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('❤️ С сердцем',callback_data='heart:yes')],[InlineKeyboardButton('Без сердца',callback_data='heart:no')]])
def layout_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('✅ Собрать',callback_data='layout:assembled')],[InlineKeyboardButton('🧩 Отдельно',callback_data='layout:separate')]])
def topper_width_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('90 мм',callback_data='topper_width:90'),InlineKeyboardButton('120 мм',callback_data='topper_width:120')],[InlineKeyboardButton('150 мм',callback_data='topper_width:150'),InlineKeyboardButton('180 мм',callback_data='topper_width:180')]])
def topper_text_height_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('2.5 мм',callback_data='topper_text_h:2.5'),InlineKeyboardButton('3.0 мм',callback_data='topper_text_h:3.0')],[InlineKeyboardButton('3.5 мм',callback_data='topper_text_h:3.5'),InlineKeyboardButton('4.0 мм',callback_data='topper_text_h:4.0')]])
def topper_backing_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('0.8 мм',callback_data='topper_backing:0.8'),InlineKeyboardButton('1.2 мм',callback_data='topper_backing:1.2')],[InlineKeyboardButton('1.6 мм',callback_data='topper_backing:1.6'),InlineKeyboardButton('2.0 мм',callback_data='topper_backing:2.0')]])
def topper_legs_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('Авто',callback_data='topper_legs:auto')],[InlineKeyboardButton('1 ножка',callback_data='topper_legs:one'),InlineKeyboardButton('2 ножки',callback_data='topper_legs:two')]])
def create_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton('✅ Создать 3MF',callback_data='create')],[InlineKeyboardButton('🔁 Начать заново',callback_data='restart')]])
def log_update(update,event):
    u=update.effective_user; c=update.effective_chat; logger.info('%s | user_id=%s username=%s chat_id=%s',event,getattr(u,'id',None),getattr(u,'username',None),getattr(c,'id',None))

async def start(update,context):
    log_update(update,'COMMAND /start'); context.user_data.clear(); await update.message.reply_text('CakeStampBot v0.8.0\n\nОставили только два режима:\n🍰 Штамп — для оттиска на креме.\n🎂 Топпер — цельная надпись с подложкой и ножкой/ножками.',reply_markup=main_menu_keyboard()); await update.message.reply_text('Выбери режим:',reply_markup=mode_inline_keyboard())
async def help_cmd(update,context):
    log_update(update,'COMMAND /help'); await update.message.reply_text('Помощь v0.8.0\n\n🍰 Штамп: текст или картинка → 3MF.\n🎂 Топпер: текст → единая модель с подложкой под буквами и ножками.\n\nВырубка удалена.',reply_markup=main_menu_keyboard())
async def queue_cmd(update,context):
    q=context.application.bot_data.get('cake_queue'); await update.message.reply_text(f'В очереди задач: {q.qsize() if q else 0}',reply_markup=main_menu_keyboard())
async def stamp_cmd(update,context):
    log_update(update,'COMMAND /stamp'); context.user_data.clear(); context.user_data['mode']='stamp'; await update.message.reply_text('Режим: 🍰 Штамп. Выбери источник:',reply_markup=source_keyboard('stamp'))
async def topper_cmd(update,context):
    log_update(update,'COMMAND /topper'); context.user_data.clear(); context.user_data['mode']='topper'; context.user_data['source']='text'; await update.message.reply_text('Режим: 🎂 Топпер.\nНапиши текст для топпера.')
async def on_text(update,context):
    log_update(update,'TEXT MESSAGE'); t=update.message.text.strip()
    if t=='🍰 Штамп': return await stamp_cmd(update,context)
    if t=='🎂 Топпер': return await topper_cmd(update,context)
    if t=='📋 Очередь': return await queue_cmd(update,context)
    if t=='ℹ️ Помощь': return await help_cmd(update,context)
    mode=context.user_data.get('mode'); source=context.user_data.get('source')
    if not mode: return await update.message.reply_text('Сначала выбери режим:',reply_markup=mode_inline_keyboard())
    if source!='text': return await update.message.reply_text('Сначала выбери «Текст» или «Картинка».',reply_markup=source_keyboard(mode))
    context.user_data['text']=t; await update.message.reply_text('Выбери шрифт:',reply_markup=font_keyboard())
async def on_photo(update,context):
    log_update(update,'PHOTO MESSAGE')
    if context.user_data.get('mode')!='stamp': return await update.message.reply_text('Картинки пока только в режиме 🍰 Штамп.',reply_markup=main_menu_keyboard())
    context.user_data['source']='image'; f=await update.message.photo[-1].get_file(); p=UPLOAD_DIR/f'{uuid.uuid4().hex[:10]}.jpg'; await f.download_to_drive(str(p)); context.user_data['image_path']=str(p); await update.message.reply_text('Картинку получил. Выбери размер штампа:',reply_markup=stamp_size_keyboard())
async def on_callback(update,context):
    q=update.callback_query; await q.answer(); data=q.data; logger.info('CALLBACK | %s',data)
    if data=='restart': context.user_data.clear(); await q.edit_message_text('Начинаем заново.'); return await q.message.reply_text('Выбери режим:',reply_markup=mode_inline_keyboard())
    if data.startswith('mode:'):
        m=data.split(':',1)[1]; context.user_data.clear(); context.user_data['mode']=m
        if m=='stamp': return await q.edit_message_text('Режим: 🍰 Штамп. Выбери источник:',reply_markup=source_keyboard('stamp'))
        context.user_data['source']='text'; return await q.edit_message_text('Режим: 🎂 Топпер. Напиши текст для топпера.')
    if data.startswith('source:'):
        s=data.split(':',1)[1]; context.user_data['source']=s; return await q.edit_message_text('Напиши текст.' if s=='text' else 'Пришли картинку или логотип.')
    if data.startswith('font:'):
        context.user_data['font_choice']=data.split(':',1)[1]
        return await q.edit_message_text('Выбери размер штампа:' if context.user_data.get('mode')=='stamp' else 'Выбери ширину топпера:', reply_markup=stamp_size_keyboard() if context.user_data.get('mode')=='stamp' else topper_width_keyboard())
    if data.startswith('stamp_size:'): context.user_data['stamp_size']=data.split(':',1)[1]; return await q.edit_message_text('Выбери форму подложки:',reply_markup=stamp_shape_keyboard())
    if data.startswith('stamp_shape:'):
        shape=data.split(':',1)[1]; context.user_data['base_shape']=shape
        if shape=='rect': return await q.edit_message_text('Выбери размер прямоугольной подложки:',reply_markup=rect_size_keyboard())
        context.user_data['base_size']=context.user_data.get('stamp_size','105'); return await q.edit_message_text('Выбери толщину линии:',reply_markup=stamp_width_keyboard())
    if data.startswith('rect_size:'): context.user_data['base_size']=data.split(':',1)[1]; return await q.edit_message_text('Выбери толщину линии:',reply_markup=stamp_width_keyboard())
    if data.startswith('stamp_width:'): context.user_data['line_width']=float(data.split(':',1)[1]); return await q.edit_message_text('Добавить сердечко?',reply_markup=heart_keyboard())
    if data.startswith('heart:'): context.user_data['add_heart']=data.split(':',1)[1]=='yes'; return await q.edit_message_text('Как расположить объекты в 3MF?',reply_markup=layout_keyboard())
    if data.startswith('layout:'): context.user_data['layout_mode']=data.split(':',1)[1]; return await show_summary(q.message,context)
    if data.startswith('topper_width:'): context.user_data['topper_width']=float(data.split(':',1)[1]); return await q.edit_message_text('Выбери высоту текста:',reply_markup=topper_text_height_keyboard())
    if data.startswith('topper_text_h:'): context.user_data['topper_text_height']=float(data.split(':',1)[1]); return await q.edit_message_text('Выбери толщину подложки под буквами:',reply_markup=topper_backing_keyboard())
    if data.startswith('topper_backing:'): context.user_data['topper_backing_height']=float(data.split(':',1)[1]); return await q.edit_message_text('Сколько ножек сделать?',reply_markup=topper_legs_keyboard())
    if data.startswith('topper_legs:'): context.user_data['topper_legs']=data.split(':',1)[1]; return await show_summary(q.message,context)
    if data=='create': return await enqueue_job(q.message,context)
async def show_summary(message,context):
    if context.user_data.get('mode')=='stamp': txt=f"Проверь настройки штампа:\n\n• размер: {str(context.user_data.get('base_size','105')).replace('x','×')} мм\n• форма: {'круглая' if context.user_data.get('base_shape')=='round' else 'прямоугольная'}\n• линия: {context.user_data.get('line_width',.45)} мм\n• сердце: {'да' if context.user_data.get('add_heart') else 'нет'}\n• раскладка: {'собрать' if context.user_data.get('layout_mode')=='assembled' else 'отдельно'}"
    else: txt=f"Проверь настройки топпера:\n\n• ширина: {context.user_data.get('topper_width',120)} мм\n• высота текста: {context.user_data.get('topper_text_height',3.0)} мм\n• подложка под буквами: {context.user_data.get('topper_backing_height',1.2)} мм\n• ножки: {context.user_data.get('topper_legs','auto')}\n\nТоппер будет цельным: текст + подложка + ножка/ножки."
    await message.reply_text(txt,reply_markup=create_keyboard())
async def enqueue_job(message,context):
    q=context.application.bot_data['cake_queue']; params=dict(context.user_data); await q.put(CakeJob(message.chat_id,params)); await message.reply_text(f'✅ Задача добавлена в очередь.\n\nПозиция: {q.qsize()}\nСоздание 3MF может занять 30–120 секунд.',reply_markup=main_menu_keyboard()); context.user_data.clear()
def build_model(params):
    out=OUTPUT_DIR/uuid.uuid4().hex[:10]
    if params.get('mode')=='topper': return build_topper_from_text(params['text'],str(out),float(params.get('topper_width',120)),params.get('font_choice','classic'),float(params.get('topper_text_height',3.0)),float(params.get('topper_backing_height',1.2)),legs=params.get('topper_legs','auto'))
    if params.get('source')=='image': return build_stamp_from_image(params['image_path'],str(out),params.get('base_size','105'),params.get('base_shape','round'),float(params.get('line_width',.45)),bool(params.get('add_heart',False)),params.get('layout_mode','assembled'))
    return build_stamp_from_text(params['text'],str(out),params.get('base_size','105'),params.get('base_shape','round'),float(params.get('line_width',.45)),params.get('font_choice','classic'),bool(params.get('add_heart',False)),params.get('layout_mode','assembled'))
async def cake_worker(app):
    logger.info('WORKER STARTED'); q=app.bot_data['cake_queue']
    while True:
        job=await q.get(); app.bot_data['cake_running']=True; logger.info('WORKER JOB START | chat_id=%s',job.chat_id)
        try:
            await app.bot.send_message(job.chat_id,'🔧 Начал обработку модели...'); result=await asyncio.to_thread(build_model,job.params)
            with open(result.preview_png,'rb') as f: await app.bot.send_photo(job.chat_id,f,caption='Превью проекта.')
            with open(result.project_3mf,'rb') as f: await app.bot.send_document(job.chat_id,f,filename=Path(result.project_3mf).name,caption='Готово ✅ Это 3MF-проект.')
            with open(result.bundle_zip,'rb') as f: await app.bot.send_document(job.chat_id,f,filename=Path(result.bundle_zip).name,caption='ZIP со STL, PNG и 3MF.',reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.exception('MODEL BUILD FAILED'); await app.bot.send_message(job.chat_id,f'Не получилось собрать модель.\n\nОшибка: {e}',reply_markup=main_menu_keyboard())
        finally:
            q.task_done(); app.bot_data['cake_running']=False; logger.info('WORKER JOB DONE | chat_id=%s',job.chat_id)
async def error_handler(update,context):
    logger.exception('Unhandled error',exc_info=context.error)
async def post_init(app):
    app.bot_data['cake_queue']=asyncio.Queue(); app.bot_data['cake_running']=False; await app.bot.set_my_commands([('start','Главное меню'),('stamp','Штамп'),('topper','Топпер'),('queue','Очередь'),('help','Помощь')]); app.bot_data['cake_worker_task']=asyncio.create_task(cake_worker(app))
async def post_shutdown(app):
    t=app.bot_data.get('cake_worker_task')
    if t: t.cancel()
def main():
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build(); app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('help',help_cmd)); app.add_handler(CommandHandler('stamp',stamp_cmd)); app.add_handler(CommandHandler('topper',topper_cmd)); app.add_handler(CommandHandler('queue',queue_cmd)); app.add_handler(CallbackQueryHandler(on_callback)); app.add_handler(MessageHandler(filters.PHOTO,on_photo)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,on_text)); app.add_error_handler(error_handler); logger.info('CakeStampBot v0.8.0 started'); print('CakeStampBot v0.8.0 started'); app.run_polling()
if __name__=='__main__': main()
