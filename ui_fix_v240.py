"""CakeStampBot v2.4.0 runtime/UI fixes."""
import asyncio
from pathlib import Path


async def _delete_message(message):
    try:
        await message.get_bot().delete_message(chat_id=message.chat_id, message_id=message.message_id)
    except Exception:
        # Deletion is cosmetic; never break the settings flow if Telegram refuses it.
        pass


def apply_fixes(app):
    async def compact_show(message, c):
        old_id = c.user_data.get("_stamp_settings_panel_id")
        if old_id:
            try:
                await message.get_bot().delete_message(chat_id=message.chat_id, message_id=int(old_id))
            except Exception:
                pass
        sent = await message.reply_text(app.panel_text(c), reply_markup=app.stamp_kb())
        c.user_data["_stamp_settings_panel_id"] = sent.message_id
        return sent

    app.show = compact_show

    original_text_router = app.text_router

    async def compact_text_router(u, c):
        text = (u.message.text or "").strip() if u.message else ""
        d = c.user_data
        # ReplyKeyboard sends every tap as a normal chat message. Remove transient
        # settings taps after the updated panel has been shown.
        clean = d.get("mode") == "stamp" and text in {
            "❤️ Сердце", "👑 Корона", "✨ Без дополнений",
            "📏 60 мм", "📏 105 мм", "📏 145 мм",
            "⭕ Круг", "▭ Прямоугольник",
            "🔤 Classic", "🔤 Comic", "🔤 GOST",
            "↕️ 10 мм", "↕️ 12 мм", "↕️ 14 мм", "↕️ 16 мм",
            "↔️ Обычный", "⬆️ Сверху", "⬇️ Снизу", "⭕ По окружности",
            "🧩 Отдельно", "🔗 Собрать",
        }
        try:
            return await original_text_router(u, c)
        finally:
            if clean and u.message:
                await _delete_message(u.message)

    app.text_router = compact_text_router

    # v2.4.0 worker: the old 210 s ceiling could discard a valid long Comic job.
    # The engine itself is now much faster, but leave enough headroom for a slow host.
    legacy = app.legacy

    async def cake_worker_v240(application):
        qq = application.bot_data["cake_queue"]
        while True:
            job = await qq.get()
            try:
                await application.bot.send_message(
                    chat_id=job.chat_id,
                    text="🔧 Начал обработку модели…\nОптимизированная векторная обработка может занять до нескольких минут.",
                )
                result = await asyncio.wait_for(
                    asyncio.to_thread(legacy.build_model, job.params),
                    timeout=420,
                )
                with open(result.preview_png, "rb") as f:
                    await application.bot.send_photo(
                        chat_id=job.chat_id,
                        photo=f,
                        caption="Превью проекта.",
                    )
                with open(result.project_3mf, "rb") as f:
                    await application.bot.send_document(
                        chat_id=job.chat_id,
                        document=f,
                        filename=Path(result.project_3mf).name,
                        caption="Готово ✅ Это 3MF-проект.",
                        reply_markup=legacy.main_menu_keyboard(),
                    )
            except asyncio.TimeoutError:
                legacy.logger.exception("CakeStampBot v2.4.0 model worker timeout")
                await application.bot.send_message(
                    chat_id=job.chat_id,
                    text="Не получилось собрать модель: превышено время обработки (420 секунд).",
                    reply_markup=legacy.main_menu_keyboard(),
                )
            except Exception as exc:
                legacy.logger.exception("CakeStampBot v2.4.0 model build failed")
                await application.bot.send_message(
                    chat_id=job.chat_id,
                    text=f"Не получилось собрать модель.\n\nОшибка: {exc}",
                    reply_markup=legacy.main_menu_keyboard(),
                )
            finally:
                qq.task_done()

    legacy.cake_worker = cake_worker_v240
