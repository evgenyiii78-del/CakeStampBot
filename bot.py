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
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from engine import build_stamp_from_text, build_stamp_from_image, build_topper_from_text

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
    force=True,
)
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


# -------------------- UI --------------------

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🍰 Штамп", "🎂 Топпер"], ["📋 Очередь", "ℹ️ Помощь"]],
        resize_keyboard=True,
    )


def mode_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🍰 Штамп", callback_data="mode:stamp")],
            [InlineKeyboardButton("🎂 Топпер", callback_data="mode:topper")],
        ]
    )


def source_keyboard(mode: str) -> InlineKeyboardMarkup:
    if mode == "topper":
        return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Текст", callback_data="source:text")]])
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✍️ Текст", callback_data="source:text")],
            [InlineKeyboardButton("🖼 Картинка / логотип", callback_data="source:image")],
        ]
    )


def font_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Classic", callback_data="font:classic"),
                InlineKeyboardButton("Comic", callback_data="font:comic"),
            ],
            [InlineKeyboardButton("GOST", callback_data="font:gost")],
        ]
    )


def stamp_size_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("60 мм", callback_data="stamp_size:60"), InlineKeyboardButton("80 мм", callback_data="stamp_size:80")],
            [InlineKeyboardButton("105 мм", callback_data="stamp_size:105"), InlineKeyboardButton("145 мм", callback_data="stamp_size:145")],
        ]
    )


def stamp_shape_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭕ Круглая", callback_data="stamp_shape:round")],
            [InlineKeyboardButton("▭ Прямоугольная", callback_data="stamp_shape:rect")],
        ]
    )


def rect_size_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("80×60", callback_data="rect_size:80x60"), InlineKeyboardButton("100×70", callback_data="rect_size:100x70")],
            [InlineKeyboardButton("105×75", callback_data="rect_size:105x75"), InlineKeyboardButton("120×80", callback_data="rect_size:120x80")],
            [InlineKeyboardButton("145×95", callback_data="rect_size:145x95")],
        ]
    )


def stamp_width_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("0.35", callback_data="stamp_width:0.35"), InlineKeyboardButton("0.45", callback_data="stamp_width:0.45")],
            [InlineKeyboardButton("0.60", callback_data="stamp_width:0.60"), InlineKeyboardButton("0.80", callback_data="stamp_width:0.80")],
        ]
    )


def heart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("❤️ С сердцем", callback_data="heart:yes")],
            [InlineKeyboardButton("Без сердца", callback_data="heart:no")],
        ]
    )


def layout_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Собрать", callback_data="layout:assembled")],
            [InlineKeyboardButton("🧩 Отдельно", callback_data="layout:separate")],
        ]
    )


def topper_width_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("90 мм", callback_data="topper_width:90"), InlineKeyboardButton("120 мм", callback_data="topper_width:120")],
            [InlineKeyboardButton("150 мм", callback_data="topper_width:150"), InlineKeyboardButton("180 мм", callback_data="topper_width:180")],
        ]
    )


def topper_text_height_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("2.5 мм", callback_data="topper_text_h:2.5"), InlineKeyboardButton("3.0 мм", callback_data="topper_text_h:3.0")],
            [InlineKeyboardButton("3.5 мм", callback_data="topper_text_h:3.5"), InlineKeyboardButton("4.0 мм", callback_data="topper_text_h:4.0")],
        ]
    )


def topper_backing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("0.8 мм", callback_data="topper_backing:0.8"), InlineKeyboardButton("1.2 мм", callback_data="topper_backing:1.2")],
            [InlineKeyboardButton("1.6 мм", callback_data="topper_backing:1.6"), InlineKeyboardButton("2.0 мм", callback_data="topper_backing:2.0")],
        ]
    )


def topper_legs_keyboard() -> InlineKeyboardMarkup:
    # В v1.1.1 поддерживаются также старые callback-префиксы legs:*
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Авто", callback_data="topper_legs:auto")],
            [InlineKeyboardButton("1 ножка", callback_data="topper_legs:one"), InlineKeyboardButton("2 ножки", callback_data="topper_legs:two")],
        ]
    )


def create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Создать 3MF", callback_data="create")],
            [InlineKeyboardButton("🔁 Начать заново", callback_data="restart")],
        ]
    )


# -------------------- Helpers --------------------

def log_update(update: Update, event: str) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info(
        "%s | user_id=%s username=%s chat_id=%s",
        event,
        getattr(user, "id", None),
        getattr(user, "username", None),
        getattr(chat, "id", None),
    )


def ensure_topper_defaults(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Позволяет не зависать, даже если пользователь попал сразу к выбору ножек."""
    context.user_data.setdefault("mode", "topper")
    context.user_data.setdefault("source", "text")
    context.user_data.setdefault("font_choice", "classic")
    context.user_data.setdefault("topper_width", 120.0)
    context.user_data.setdefault("topper_text_height", 3.0)
    context.user_data.setdefault("topper_backing_height", 1.2)
    context.user_data.setdefault("topper_legs", "auto")


def stamp_summary_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (
        "Проверь настройки штампа:\n\n"
        f"• источник: {'текст' if context.user_data.get('source') == 'text' else 'картинка'}\n"
        f"• размер: {str(context.user_data.get('base_size', '105')).replace('x', '×')} мм\n"
        f"• форма: {'круглая' if context.user_data.get('base_shape') == 'round' else 'прямоугольная'}\n"
        f"• линия: {context.user_data.get('line_width', 0.45)} мм\n"
        f"• сердце: {'да' if context.user_data.get('add_heart') else 'нет'}\n"
        f"• раскладка: {'собрать' if context.user_data.get('layout_mode') == 'assembled' else 'отдельно'}"
    )


def topper_summary_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    ensure_topper_defaults(context)
    legs = context.user_data.get("topper_legs", "auto")
    legs_ru = {"auto": "авто", "one": "1 ножка", "two": "2 ножки"}.get(legs, str(legs))
    return (
        "Проверь настройки топпера:\n\n"
        f"• ширина: {context.user_data.get('topper_width', 120)} мм\n"
        f"• высота текста: {context.user_data.get('topper_text_height', 3.0)} мм\n"
        f"• подложка под буквами: {context.user_data.get('topper_backing_height', 1.2)} мм\n"
        f"• ножки: {legs_ru}\n\n"
        "Топпер будет цельным: текст + подложка под буквами + ножка/ножки."
    )


async def send_or_edit_summary(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("mode") == "stamp":
        text = stamp_summary_text(context)
    else:
        text = topper_summary_text(context)
    await query.edit_message_text(text, reply_markup=create_keyboard())


# -------------------- Commands --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "COMMAND /start")
    context.user_data.clear()
    await update.message.reply_text(
        "CakeStampBot v1.1.1\n\n"
        "Оставили только два режима:\n"
        "🍰 Штамп — полнотелый векторный рельеф для оттиска на креме.\n"
        "🎂 Топпер — TextBase по буквам, две перемычки между строками, ножка отдельно.",
        reply_markup=main_menu_keyboard(),
    )
    await update.message.reply_text("Выбери режим:", reply_markup=mode_inline_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "COMMAND /help")
    await update.message.reply_text(
        "Помощь CakeStampBot v1.1.1\n\n"
        "🍰 Штамп: текст или картинка → 3MF.\n"
        "🎂 Топпер: текст → единая модель с подложкой под буквами и ножками.\n\n"
        "Вырубка удалена из проекта.",
        reply_markup=main_menu_keyboard(),
    )


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "COMMAND /queue")
    q = context.application.bot_data.get("cake_queue")
    await update.message.reply_text(f"В очереди задач: {q.qsize() if q else 0}", reply_markup=main_menu_keyboard())


async def stamp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "COMMAND /stamp")
    context.user_data.clear()
    context.user_data["mode"] = "stamp"
    await update.message.reply_text("Режим: 🍰 Штамп. Выбери источник:", reply_markup=source_keyboard("stamp"))


async def topper_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "COMMAND /topper")
    context.user_data.clear()
    context.user_data["mode"] = "topper"
    context.user_data["source"] = "text"
    await update.message.reply_text("Режим: 🎂 Топпер. Напиши текст для топпера.")


# -------------------- Message handlers --------------------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "TEXT MESSAGE")
    text = update.message.text.strip()

    if text == "🍰 Штамп":
        await stamp_cmd(update, context)
        return
    if text == "🎂 Топпер":
        await topper_cmd(update, context)
        return
    if text == "📋 Очередь":
        await queue_cmd(update, context)
        return
    if text == "ℹ️ Помощь":
        await help_cmd(update, context)
        return

    # Fallback на случай, если Telegram/клиент отправит текст кнопки вместо callback.
    if context.user_data.get("mode") == "topper" and context.user_data.get("text"):
        normalized = text.lower().replace("ё", "е")
        if normalized in {"авто", "auto"}:
            ensure_topper_defaults(context)
            context.user_data["topper_legs"] = "auto"
            await update.message.reply_text(topper_summary_text(context), reply_markup=create_keyboard())
            return
        if normalized in {"1 ножка", "одна ножка", "1", "одна"}:
            ensure_topper_defaults(context)
            context.user_data["topper_legs"] = "one"
            await update.message.reply_text(topper_summary_text(context), reply_markup=create_keyboard())
            return
        if normalized in {"2 ножки", "две ножки", "2", "две"}:
            ensure_topper_defaults(context)
            context.user_data["topper_legs"] = "two"
            await update.message.reply_text(topper_summary_text(context), reply_markup=create_keyboard())
            return

    mode = context.user_data.get("mode")
    source = context.user_data.get("source")

    if not mode:
        await update.message.reply_text("Сначала выбери режим:", reply_markup=mode_inline_keyboard())
        return

    if source != "text":
        await update.message.reply_text("Сначала выбери «Текст» или «Картинка».", reply_markup=source_keyboard(mode))
        return

    context.user_data["text"] = text
    await update.message.reply_text("Выбери шрифт:", reply_markup=font_keyboard())


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_update(update, "PHOTO MESSAGE")

    if context.user_data.get("mode") != "stamp":
        await update.message.reply_text("Картинки пока только в режиме 🍰 Штамп.", reply_markup=main_menu_keyboard())
        return

    context.user_data["source"] = "image"
    file = await update.message.photo[-1].get_file()
    image_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}.jpg"
    await file.download_to_drive(str(image_path))
    context.user_data["image_path"] = str(image_path)

    await update.message.reply_text("Картинку получил. Выбери размер штампа:", reply_markup=stamp_size_keyboard())


# -------------------- Callback handler --------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    logger.info("CALLBACK | data=%s user_id=%s", data, getattr(query.from_user, "id", None))

    try:
        if data == "restart":
            context.user_data.clear()
            await query.edit_message_text("Начинаем заново. Выбери режим:", reply_markup=mode_inline_keyboard())
            return

        if data.startswith("mode:"):
            mode = data.split(":", 1)[1]
            context.user_data.clear()
            context.user_data["mode"] = mode
            if mode == "stamp":
                await query.edit_message_text("Режим: 🍰 Штамп. Выбери источник:", reply_markup=source_keyboard("stamp"))
            else:
                context.user_data["source"] = "text"
                await query.edit_message_text("Режим: 🎂 Топпер. Напиши текст для топпера.")
            return

        if data.startswith("source:"):
            source = data.split(":", 1)[1]
            context.user_data["source"] = source
            await query.edit_message_text("Напиши текст." if source == "text" else "Пришли картинку или логотип.")
            return

        if data.startswith("font:"):
            context.user_data["font_choice"] = data.split(":", 1)[1]
            if context.user_data.get("mode") == "stamp":
                await query.edit_message_text("Выбери размер штампа:", reply_markup=stamp_size_keyboard())
            else:
                ensure_topper_defaults(context)
                await query.edit_message_text("Выбери ширину топпера:", reply_markup=topper_width_keyboard())
            return

        # Stamp flow
        if data.startswith("stamp_size:"):
            context.user_data["stamp_size"] = data.split(":", 1)[1]
            await query.edit_message_text("Выбери форму подложки:", reply_markup=stamp_shape_keyboard())
            return

        if data.startswith("stamp_shape:"):
            shape = data.split(":", 1)[1]
            context.user_data["base_shape"] = shape
            if shape == "rect":
                await query.edit_message_text("Выбери размер прямоугольной подложки:", reply_markup=rect_size_keyboard())
            else:
                context.user_data["base_size"] = context.user_data.get("stamp_size", "105")
                await query.edit_message_text("Выбери толщину линии:", reply_markup=stamp_width_keyboard())
            return

        if data.startswith("rect_size:"):
            context.user_data["base_size"] = data.split(":", 1)[1]
            await query.edit_message_text("Выбери толщину линии:", reply_markup=stamp_width_keyboard())
            return

        if data.startswith("stamp_width:"):
            context.user_data["line_width"] = float(data.split(":", 1)[1])
            await query.edit_message_text("Добавить сердечко?", reply_markup=heart_keyboard())
            return

        if data.startswith("heart:"):
            context.user_data["add_heart"] = data.split(":", 1)[1] == "yes"
            await query.edit_message_text("Как расположить объекты в 3MF?", reply_markup=layout_keyboard())
            return

        if data.startswith("layout:"):
            context.user_data["layout_mode"] = data.split(":", 1)[1]
            await send_or_edit_summary(query, context)
            return

        # Topper flow
        if data.startswith("topper_width:"):
            ensure_topper_defaults(context)
            context.user_data["topper_width"] = float(data.split(":", 1)[1])
            await query.edit_message_text("Выбери высоту текста:", reply_markup=topper_text_height_keyboard())
            return

        if data.startswith("topper_text_h:"):
            ensure_topper_defaults(context)
            context.user_data["topper_text_height"] = float(data.split(":", 1)[1])
            await query.edit_message_text("Выбери толщину подложки под буквами:", reply_markup=topper_backing_keyboard())
            return

        if data.startswith("topper_backing:"):
            ensure_topper_defaults(context)
            context.user_data["topper_backing_height"] = float(data.split(":", 1)[1])
            await query.edit_message_text("Сколько ножек сделать?", reply_markup=topper_legs_keyboard())
            return

        # v1.1.1: поддерживаем topper_legs:*, topper_leg:* и старый legs:*.
        if data.startswith("topper_legs:") or data.startswith("topper_leg:") or data.startswith("legs:"):
            ensure_topper_defaults(context)
            context.user_data["topper_legs"] = data.split(":", 1)[1]
            await send_or_edit_summary(query, context)
            return

        if data == "create":
            await enqueue_job(query.message, context)
            return

        logger.warning("UNKNOWN CALLBACK | data=%s", data)
        await query.edit_message_text("Не понял кнопку. Начни заново:", reply_markup=mode_inline_keyboard())

    except Exception:
        logger.exception("Callback processing failed | data=%s", data)
        await query.message.reply_text(
            "Кнопка не обработалась из-за ошибки. Я записал её в логи. Попробуй /start.",
            reply_markup=main_menu_keyboard(),
        )


# -------------------- Queue and build --------------------

async def enqueue_job(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = context.application.bot_data["cake_queue"]

    if context.user_data.get("mode") == "topper":
        ensure_topper_defaults(context)

    params = dict(context.user_data)
    chat_id = message.chat_id

    # v1.1.1 hotfix: do not enqueue a topper job without saved text.
    # This prevents the old error: KeyError('text').
    if params.get("mode") == "topper" and not params.get("text"):
        logger.warning("TOPPER CREATE WITHOUT TEXT | chat_id=%s params=%s", chat_id, params)
        context.user_data.clear()
        context.user_data["mode"] = "topper"
        context.user_data["source"] = "text"
        await message.reply_text(
            "Я потерял текст топпера. Напиши текст ещё раз, и я продолжу.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if params.get("mode") == "stamp" and params.get("source") == "text" and not params.get("text"):
        logger.warning("STAMP CREATE WITHOUT TEXT | chat_id=%s params=%s", chat_id, params)
        context.user_data.clear()
        context.user_data["mode"] = "stamp"
        context.user_data["source"] = "text"
        await message.reply_text(
            "Я потерял текст штампа. Напиши текст ещё раз.",
            reply_markup=main_menu_keyboard(),
        )
        return

    logger.info("QUEUE ADD | chat_id=%s params=%s", chat_id, params)
    await q.put(CakeJob(chat_id=chat_id, params=params))

    await message.reply_text(
        "✅ Задача добавлена в очередь.\n\n"
        f"Позиция: {q.qsize()}\n"
        "Создание 3MF может занять 30–120 секунд.",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.clear()


def build_model(params: dict[str, Any]):
    out_dir = OUTPUT_DIR / uuid.uuid4().hex[:10]

    if params.get("mode") == "topper":
        text = params.get("text")
        if not text:
            raise RuntimeError("Не найден текст топпера. Начните топпер заново и введите текст.")
        return build_topper_from_text(
            text=text,
            output_dir=str(out_dir),
            width_mm=float(params.get("topper_width", 120)),
            font_choice=params.get("font_choice", "classic"),
            text_height=float(params.get("topper_text_height", 3.0)),
            backing_height=float(params.get("topper_backing_height", 1.2)),
            legs=params.get("topper_legs", "auto"),
        )

    if params.get("source") == "image":
        return build_stamp_from_image(
            image_path=params["image_path"],
            output_dir=str(out_dir),
            base_size=params.get("base_size", "105"),
            base_shape=params.get("base_shape", "round"),
            line_width=float(params.get("line_width", 0.45)),
            add_heart=bool(params.get("add_heart", False)),
            layout_mode=params.get("layout_mode", "assembled"),
        )

    text = params.get("text")
    if not text:
        raise RuntimeError("Не найден текст штампа. Начните штамп заново и введите текст.")
    return build_stamp_from_text(
        text=text,
        output_dir=str(out_dir),
        base_size=params.get("base_size", "105"),
        base_shape=params.get("base_shape", "round"),
        line_width=float(params.get("line_width", 0.45)),
        font_choice=params.get("font_choice", "classic"),
        add_heart=bool(params.get("add_heart", False)),
        layout_mode=params.get("layout_mode", "assembled"),
    )


async def cake_worker(app: Application) -> None:
    logger.info("WORKER STARTED")
    q = app.bot_data["cake_queue"]

    while True:
        job = await q.get()
        app.bot_data["cake_running"] = True
        logger.info("WORKER JOB START | chat_id=%s", job.chat_id)

        try:
            await app.bot.send_message(chat_id=job.chat_id, text="🔧 Начал обработку модели...\nВекторный топпер может занять 30–120 секунд.")
            result = await asyncio.wait_for(asyncio.to_thread(build_model, job.params), timeout=210)

            with open(result.preview_png, "rb") as f:
                await app.bot.send_photo(chat_id=job.chat_id, photo=f, caption="Превью проекта.")

            with open(result.project_3mf, "rb") as f:
                await app.bot.send_document(
                    chat_id=job.chat_id,
                    document=f,
                    filename=Path(result.project_3mf).name,
                    caption="Готово ✅ Это 3MF-проект.",
                )

            with open(result.bundle_zip, "rb") as f:
                await app.bot.send_document(
                    chat_id=job.chat_id,
                    document=f,
                    filename=Path(result.bundle_zip).name,
                    caption="ZIP со STL, PNG и 3MF.",
                    reply_markup=main_menu_keyboard(),
                )

        except Exception as exc:
            logger.exception("MODEL BUILD FAILED | chat_id=%s", job.chat_id)
            await app.bot.send_message(
                chat_id=job.chat_id,
                text=f"Не получилось собрать модель.\n\nОшибка: {exc}",
                reply_markup=main_menu_keyboard(),
            )
        finally:
            q.task_done()
            app.bot_data["cake_running"] = False
            logger.info("WORKER JOB DONE | chat_id=%s", job.chat_id)


# -------------------- App --------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update: %s", update, exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Произошла ошибка. Она записана в логи.")
    except Exception:
        logger.exception("Failed to send error message to user")


async def post_init(app: Application) -> None:
    app.bot_data["cake_queue"] = asyncio.Queue()
    app.bot_data["cake_running"] = False
    await app.bot.set_my_commands(
        [
            ("start", "Главное меню"),
            ("stamp", "Штамп"),
            ("topper", "Топпер"),
            ("queue", "Очередь"),
            ("help", "Помощь"),
        ]
    )
    app.bot_data["cake_worker_task"] = asyncio.create_task(cake_worker(app))


async def post_shutdown(app: Application) -> None:
    task = app.bot_data.get("cake_worker_task")
    if task:
        task.cancel()


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stamp", stamp_cmd))
    app.add_handler(CommandHandler("topper", topper_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(error_handler)

    logger.info("CakeStampBot v1.1.1 started")
    print("CakeStampBot v1.1.1 started")
    app.run_polling()


if __name__ == "__main__":
    main()
