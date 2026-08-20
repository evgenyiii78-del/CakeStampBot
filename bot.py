import os
import uuid
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from engine import generate_text_project, generate_image_project


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Создай .env и впиши токен бота.")

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CakeJob:
    chat_id: int
    params: dict[str, Any]


def kb(rows):
    return InlineKeyboardMarkup(rows)


def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🍰 Новый проект"],
            ["✍️ Текст", "🖼 Картинка"],
            ["📋 Очередь", "ℹ️ Помощь"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери действие",
    )


def source_keyboard():
    return kb([
        [
            InlineKeyboardButton("✍️ Текст", callback_data="source:text"),
            InlineKeyboardButton("🖼 Картинка", callback_data="source:image"),
        ],
    ])


def mode_keyboard():
    return kb([
        [InlineKeyboardButton("🍰 Штамп", callback_data="mode:stamp")],
        [
            InlineKeyboardButton("🎂 Топпер", callback_data="mode:topper"),
            InlineKeyboardButton("🍪 Вырубка", callback_data="mode:cutter"),
        ],
    ])


def font_keyboard():
    return kb([
        [
            InlineKeyboardButton("Classic", callback_data="font:classic"),
            InlineKeyboardButton("Comic Sans", callback_data="font:comic"),
        ],
        [InlineKeyboardButton("GOST type AU", callback_data="font:gost")],
    ])


def size_keyboard():
    return kb([
        [
            InlineKeyboardButton("60 мм", callback_data="size:60"),
            InlineKeyboardButton("80 мм", callback_data="size:80"),
        ],
        [
            InlineKeyboardButton("105 мм", callback_data="size:105"),
            InlineKeyboardButton("145 мм", callback_data="size:145"),
        ],
    ])


def base_shape_keyboard():
    return kb([
        [
            InlineKeyboardButton("⭕ Круглая", callback_data="shape:round"),
            InlineKeyboardButton("▭ Прямоугольная", callback_data="shape:rect"),
        ],
    ])


def width_keyboard():
    return kb([
        [
            InlineKeyboardButton("0.35 мм", callback_data="width:0.35"),
            InlineKeyboardButton("0.45 мм", callback_data="width:0.45"),
        ],
        [
            InlineKeyboardButton("0.60 мм", callback_data="width:0.60"),
            InlineKeyboardButton("0.80 мм", callback_data="width:0.80"),
        ],
    ])


def heart_keyboard():
    return kb([
        [
            InlineKeyboardButton("❤️ Да", callback_data="heart:yes"),
            InlineKeyboardButton("Без сердца", callback_data="heart:no"),
        ],
    ])


def create_keyboard():
    return kb([
        [InlineKeyboardButton("🚀 Создать 3MF", callback_data="create")],
        [InlineKeyboardButton("↩️ Начать заново", callback_data="restart")],
    ])


async def send_project_menu(message):
    await message.reply_text(
        "Выбери, что делаем дальше:",
        reply_markup=source_keyboard(),
    )



def format_base_size(value) -> str:
    raw = str(value or "105").replace("x", "×")
    try:
        return f"{int(float(raw))} мм"
    except ValueError:
        return f"{raw} мм"


async def show_summary_for_create(message, context: ContextTypes.DEFAULT_TYPE):
    await message.reply_text(
        summary_text(context.user_data),
        reply_markup=create_keyboard(),
    )


def should_ask_heart(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.user_data.get("product_mode") in ("stamp", "topper")


def should_ask_layout(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.user_data.get("product_mode") == "stamp"




async def go_next_after_core_options(message, context: ContextTypes.DEFAULT_TYPE, prefix: str = ""):
    """
    Robust settings flow:
    - line_width must be selected
    - heart is asked only once for stamp/topper
    - layout is asked only once for stamp
    - then show final summary/create button
    """
    if "line_width" not in context.user_data:
        await message.reply_text(
            (prefix + "\n\n" if prefix else "") + "Выбери толщину линии:",
            reply_markup=width_keyboard(),
        )
        return

    if should_ask_heart(context) and "add_heart" not in context.user_data:
        await message.reply_text(
            (prefix + "\n\n" if prefix else "") + "Добавить сердечко отдельным объектом?",
            reply_markup=heart_keyboard(),
        )
        return

    if not should_ask_heart(context):
        context.user_data["add_heart"] = False

    if should_ask_layout(context) and "layout_mode" not in context.user_data:
        await message.reply_text(
            (prefix + "\n\n" if prefix else "") + "Как расположить объекты в 3MF?",
            reply_markup=layout_keyboard(),
        )
        return

    if not should_ask_layout(context):
        context.user_data["layout_mode"] = "separate"

    await message.reply_text(
        (prefix + "\n\n" if prefix else "") + "Настройки готовы ✅"
    )
    await show_summary_for_create(message, context)


def summary_text(params: dict[str, Any]) -> str:
    source = "Текст" if params.get("source") == "text" else "Картинка"
    mode_map = {
        "stamp": "Штамп",
        "topper": "Топпер",
        "cutter": "Вырубка",
    }
    mode = mode_map.get(params.get("product_mode"), params.get("product_mode"))
    font = params.get("font_choice", "classic")
    heart = "да" if params.get("add_heart") else "нет"
    shape = params.get("base_shape", "round")
    shape_text = "круглая" if shape == "round" else "прямоугольная"

    parts = [
        "Проверь настройки:",
        "",
        f"Источник: {source}",
        f"Режим: {mode}",
        f"Размер: {format_base_size(params.get('base_diameter', 105))}",
    ]

    if params.get("product_mode") == "stamp":
        parts.append(f"Подложка: {shape_text}")

    parts.extend([
        f"Толщина линии: {params.get('line_width', 0.45)} мм",
        f"Сердечко: {heart}",
        f"Шрифт: {font if source == 'Текст' else '-'}",
    ])

    if params.get("product_mode") == "stamp":
        layout = params.get("layout_mode", "separate")
        parts.append(f"Раскладка: {'собрать на подложке' if layout == 'assembled' else 'отдельные объекты'}")

    return "\n".join(parts)




def rect_size_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("80×60", callback_data="rectsize:80x60"),
            InlineKeyboardButton("100×70", callback_data="rectsize:100x70"),
        ],
        [
            InlineKeyboardButton("105×75", callback_data="rectsize:105x75"),
            InlineKeyboardButton("120×80", callback_data="rectsize:120x80"),
        ],
        [
            InlineKeyboardButton("145×95", callback_data="rectsize:145x95"),
        ],
    ])


def layout_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧩 Отдельно", callback_data="layout:separate"),
            InlineKeyboardButton("✅ Собрать", callback_data="layout:assembled"),
        ],
    ])


def final_preview_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Создать 3MF", callback_data="make3mf"),
            InlineKeyboardButton("🔁 Настройки", callback_data="restart_settings"),
        ],
    ])



def line_width_keyboard():
    # Backward-compatible alias. Older callback flow uses this name.
    return width_keyboard()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🍰 CakeStampBot v0.7.4\n\n"
        "Главное меню всегда внизу — команды вручную вводить не нужно.\n\n"
        "Можно сделать:\n"
        "• штамп для крема\n"
        "• топпер\n"
        "• вырубку\n\n"
        "Для штампа можно выбрать форму подложки: круглая или прямоугольная.",
        reply_markup=main_menu_keyboard(),
    )
    await send_project_menu(update.message)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Помощь по CakeStampBot v0.7.4\n\n"
        "Кнопки внизу:\n"
        "🍰 Новый проект — начать заново\n"
        "✍️ Текст — модель из текста\n"
        "🖼 Картинка — модель из картинки\n"
        "📋 Очередь — посмотреть очередь\n\n"
        "Параметры:\n"
        "• штамп / топпер / вырубка\n"
        "• круглая / прямоугольная подложка для штампа\n"
        "• выбор толщины линии\n"
        "• выбор сердечка\n"
        "• выбор шрифта\n"
        "• 3MF с отдельными объектами",
        reply_markup=main_menu_keyboard(),
    )


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q: asyncio.Queue = context.application.bot_data["cake_queue"]
    running = context.application.bot_data.get("cake_running", False)
    await update.message.reply_text(
        f"Очередь: {q.qsize()} задач.\n"
        f"Сейчас обрабатывается: {'да' if running else 'нет'}",
        reply_markup=main_menu_keyboard(),
    )


async def text_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["source"] = "text"
    await update.message.reply_text(
        "Выбери тип изделия:",
        reply_markup=mode_keyboard(),
    )


async def stamp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["source"] = "image"
    await update.message.reply_text(
        "Выбери тип изделия:",
        reply_markup=mode_keyboard(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "restart":
        context.user_data.clear()
        await query.edit_message_text(
            "Начинаем заново. Выбери источник:",
            reply_markup=source_keyboard(),
        )
        return

    if data.startswith("source:"):
        context.user_data.clear()
        context.user_data["source"] = data.split(":")[1]
        await query.edit_message_text(
            "Выбери тип изделия:",
            reply_markup=mode_keyboard(),
        )
        return

    if data.startswith("mode:"):
        context.user_data["product_mode"] = data.split(":")[1]

        if context.user_data.get("source") == "text":
            context.user_data["state"] = "awaiting_text"
            await query.edit_message_text(
                "Напиши текст для модели.\n\n"
                "Пример:\n"
                "С Днём\nРождения\nТанечка!"
            )
        else:
            context.user_data["state"] = "awaiting_image"
            await query.edit_message_text(
                "Пришли картинку или логотип.\n\n"
                "Лучше всего: чёрный рисунок на белом фоне."
            )
        return

    if data.startswith("font:"):
        context.user_data["font_choice"] = data.split(":")[1]
        await query.edit_message_text(
            "Выбери размер:",
            reply_markup=size_keyboard(),
        )
        return

    if data.startswith("size:"):
        context.user_data["base_diameter"] = data.split(":")[1]

        if context.user_data.get("product_mode") == "stamp":
            await query.edit_message_text(
                "Выбери форму подложки:",
                reply_markup=base_shape_keyboard(),
            )
        else:
            context.user_data["base_shape"] = "none"
            await query.edit_message_text(
                "Выбери толщину линии:",
                reply_markup=width_keyboard(),
            )
        return

    if data.startswith("shape:"):
        base_shape = data.split(":")[1]
        context.user_data["base_shape"] = base_shape

        if base_shape == "rect":
            await query.edit_message_text(
                "Форма подложки: прямоугольная.\n\n"
                "Выбери размер прямоугольника:",
                reply_markup=rect_size_keyboard(),
            )
            return

        await query.edit_message_text(
            "Форма подложки: круглая.\n\n"
            "Теперь выбери толщину линии:",
            reply_markup=width_keyboard(),
        )
        return

    if data.startswith("rectsize:"):
        rect_size = data.split(":")[1]
        context.user_data["base_diameter"] = rect_size
        context.user_data["base_shape"] = "rect"

        await query.edit_message_text(
            f"Размер прямоугольника: {rect_size.replace('x', '×')} мм.\n\n"
            "Теперь выбери толщину линии:",
            reply_markup=width_keyboard(),
        )
        return

    if data.startswith("width:"):
        context.user_data["line_width"] = float(data.split(":")[1])
        await query.edit_message_text(
            f"Толщина линии: {context.user_data['line_width']} мм."
        )
        await go_next_after_core_options(query.message, context)
        return

    if data.startswith("heart:"):
        add_heart = data.split(":")[1] == "yes"
        context.user_data["add_heart"] = add_heart
        await query.edit_message_text(
            f"Сердечко: {'да' if add_heart else 'нет'}."
        )
        await go_next_after_core_options(query.message, context)
        return

    if data.startswith("layout:"):
        layout_mode = data.split(":")[1]
        context.user_data["layout_mode"] = layout_mode
        await query.edit_message_text(
            f"Раскладка: {'собрать на подложке' if layout_mode == 'assembled' else 'отдельные объекты'}."
        )
        await go_next_after_core_options(query.message, context)
        return

    if data == "restart_settings":
        await query.edit_message_text(
            "Хорошо, выбери размер заново:",
            reply_markup=size_keyboard(),
        )
        return

    # Old v0.7 buttons compatibility.
    if data == "make3mf":
        await _enqueue_job(query.message, context)
        return

    if data == "create":
        await _enqueue_job(query.message, context)
        return




async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_value = (update.message.text or "").strip()
    state = context.user_data.get("state")

    if state != "awaiting_text":
        if text_value in ("🍰 Новый проект", "Новый проект", "Меню"):
            context.user_data.clear()
            await update.message.reply_text(
                "Начинаем новый проект ✅",
                reply_markup=main_menu_keyboard(),
            )
            await send_project_menu(update.message)
            return

        if text_value in ("✍️ Текст", "Текст"):
            await text_cmd(update, context)
            return

        if text_value in ("🖼 Картинка", "Картинка"):
            await stamp_cmd(update, context)
            return

        if text_value in ("📋 Очередь", "Очередь"):
            await queue_cmd(update, context)
            return

        if text_value in ("ℹ️ Помощь", "Помощь"):
            await help_cmd(update, context)
            return

        await update.message.reply_text(
            "Выбери действие кнопками внизу 👇\n\n"
            "Или нажми «🍰 Новый проект».",
            reply_markup=main_menu_keyboard(),
        )
        return

    context.user_data["text"] = update.message.text
    context.user_data["state"] = None

    await update.message.reply_text(
        "Выбери шрифт:",
        reply_markup=font_keyboard(),
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if state != "awaiting_image":
        context.user_data.clear()
        context.user_data["source"] = "image"
        context.user_data["product_mode"] = "stamp"

    photo = update.message.photo[-1]
    file = await photo.get_file()

    job_id = uuid.uuid4().hex[:10]
    image_path = UPLOAD_DIR / f"{job_id}.jpg"
    await file.download_to_drive(str(image_path))

    context.user_data["image_path"] = str(image_path)
    context.user_data["state"] = None

    await update.message.reply_text(
        "Картинку получил ✅\n\n"
        "Выбери размер:",
        reply_markup=size_keyboard(),
    )


async def _enqueue_job(message, context: ContextTypes.DEFAULT_TYPE):
    params = dict(context.user_data)

    if not params.get("source") or not params.get("product_mode"):
        await message.reply_text(
            "Не хватает настроек. Нажми «🍰 Новый проект» и попробуй заново.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if params.get("source") == "text" and not params.get("text"):
        await message.reply_text(
            "Нет текста. Нажми «✍️ Текст» и попробуй заново.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if params.get("source") == "image" and not params.get("image_path"):
        await message.reply_text(
            "Нет картинки. Нажми «🖼 Картинка» и попробуй заново.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if params.get("product_mode") == "stamp" and not params.get("base_shape"):
        params["base_shape"] = "round"

    q: asyncio.Queue = context.application.bot_data["cake_queue"]
    chat_id = message.chat_id
    await q.put(CakeJob(chat_id=chat_id, params=params))
    pos = q.qsize()

    await message.reply_text(
        "✅ Задача добавлена в очередь.\n\n"
        f"Позиция: {pos}\n"
        "Если модель сложная, создание 3MF может занять 30–120 секунд.\n"
        "Когда обработка закончится, я пришлю PNG, 3MF и ZIP.",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.clear()


async def cake_worker(app: Application):
    q: asyncio.Queue = app.bot_data["cake_queue"]

    while True:
        job: CakeJob = await q.get()
        app.bot_data["cake_running"] = True

        try:
            await app.bot.send_message(
                chat_id=job.chat_id,
                text="🔧 Начал обработку модели...",
            )

            params = job.params
            out_dir = OUTPUT_DIR / uuid.uuid4().hex[:10]
            base_shape = params.get("base_shape", "round")

            if params.get("source") == "text":
                result = await asyncio.to_thread(
                    generate_text_project,
                    params["text"],
                    str(out_dir),
                    params.get("product_mode", "stamp"),
                    params.get("base_diameter", 105),
                    float(params.get("line_width", 0.45)),
                    bool(params.get("add_heart", True)),
                    params.get("font_choice", "classic"),
                    base_shape,
                    params.get("layout_mode", "separate"),
                )
            else:
                result = await asyncio.to_thread(
                    generate_image_project,
                    params["image_path"],
                    str(out_dir),
                    params.get("product_mode", "stamp"),
                    params.get("base_diameter", 105),
                    float(params.get("line_width", 0.45)),
                    bool(params.get("add_heart", False)),
                    base_shape,
                    params.get("layout_mode", "separate"),
                )

            with open(result.preview_png, "rb") as f:
                await app.bot.send_photo(
                    chat_id=job.chat_id,
                    photo=f,
                    caption="Превью проекта.",
                )

            with open(result.project_3mf, "rb") as f:
                await app.bot.send_document(
                    chat_id=job.chat_id,
                    document=f,
                    filename=Path(result.project_3mf).name,
                    caption=(
                        "Готово ✅\n\n"
                        "Это 3MF-проект. Объекты внутри отдельные, "
                        "можно двигать и масштабировать в слайсере."
                    ),
                )

            with open(result.bundle_zip, "rb") as f:
                await app.bot.send_document(
                    chat_id=job.chat_id,
                    document=f,
                    filename=Path(result.bundle_zip).name,
                    caption="ZIP со STL, PNG и 3MF.",
                    reply_markup=main_menu_keyboard(),
                )

        except Exception as e:
            await app.bot.send_message(
                chat_id=job.chat_id,
                text=(
                    "Не получилось собрать модель.\n\n"
                    f"Ошибка: {e}\n\n"
                    "Попробуй более простую картинку или режим «✍️ Текст»."
                ),
                reply_markup=main_menu_keyboard(),
            )

        finally:
            q.task_done()
            app.bot_data["cake_running"] = False


async def post_init(app: Application):
    app.bot_data["cake_queue"] = asyncio.Queue()
    app.bot_data["cake_running"] = False
    await app.bot.set_my_commands([
        ("start", "Главное меню"),
        ("text", "Модель из текста"),
        ("stamp", "Модель из картинки"),
        ("queue", "Очередь задач"),
        ("help", "Помощь"),
    ])
    app.bot_data['cake_worker_task'] = asyncio.create_task(cake_worker(app))



async def post_shutdown(app: Application):
    task = app.bot_data.get("cake_worker_task")
    if task:
        task.cancel()



async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("BOT ERROR:", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка в обработке кнопки. Нажми «🍰 Новый проект» и попробуй заново.",
            reply_markup=main_menu_keyboard(),
        )


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("text", text_cmd))
    app.add_handler(CommandHandler("stamp", stamp_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("CakeStampBot v0.7.4 started")
    app.run_polling()


if __name__ == "__main__":
    main()
