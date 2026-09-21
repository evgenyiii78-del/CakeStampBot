"""CakeStampBot v2.4.5 runtime/UI fixes.

Adds resilient Telegram delivery: generated preview/3MF files are retried on
telegram.error.TimedOut/NetworkError instead of being reported as a model-build
failure. Model generation and Telegram delivery are handled as separate stages.
"""
import asyncio
from pathlib import Path

from telegram.error import NetworkError, TimedOut


async def _delete_message(message):
    try:
        await message.get_bot().delete_message(chat_id=message.chat_id, message_id=message.message_id)
    except Exception:
        # Deletion is cosmetic; never break the settings flow if Telegram refuses it.
        pass


async def _telegram_retry(operation, *, attempts=4):
    """Retry transient Telegram transport errors with short exponential backoff."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            await asyncio.sleep(min(8.0, 1.5 * (2 ** (attempt - 1))))
    if last_error is not None:
        raise last_error


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
        clean = d.get("mode") == "stamp" and text in {
            "❤️ Сердце", "👑 Корона", "✨ Без дополнений",
            "📏 60 мм", "📏 105 мм", "📏 130 мм", "📏 145 мм",
            "⭕ Круг", "▭ Прямоугольник",
            "🔤 Classic", "✍️ Рукописный", "🔤 Comic", "🔤 GOST",
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

    legacy = app.legacy

    async def cake_worker_v245(application):
        qq = application.bot_data["cake_queue"]
        while True:
            job = await qq.get()
            result = None
            try:
                async def send_started():
                    return await application.bot.send_message(
                        chat_id=job.chat_id,
                        text="🔧 Начал обработку модели…\nОптимизированная векторная обработка может занять до нескольких минут.",
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=20,
                        pool_timeout=20,
                    )

                await _telegram_retry(send_started, attempts=3)

                # Stage 1: build the model. This timeout is independent of Telegram I/O.
                result = await asyncio.wait_for(
                    asyncio.to_thread(legacy.build_model, job.params),
                    timeout=420,
                )

                # Stage 2: send preview. Re-open on every retry so the file pointer
                # is correct after a failed upload attempt.
                async def send_preview():
                    with open(result.preview_png, "rb") as f:
                        return await application.bot.send_photo(
                            chat_id=job.chat_id,
                            photo=f,
                            caption="Превью проекта.",
                            read_timeout=60,
                            write_timeout=120,
                            connect_timeout=30,
                            pool_timeout=30,
                        )

                await _telegram_retry(send_preview, attempts=4)

                # Stage 3: send 3MF. Give document uploads more time on Bothost.
                async def send_project():
                    with open(result.project_3mf, "rb") as f:
                        return await application.bot.send_document(
                            chat_id=job.chat_id,
                            document=f,
                            filename=Path(result.project_3mf).name,
                            caption="Готово ✅ Это 3MF-проект.",
                            reply_markup=legacy.main_menu_keyboard(),
                            read_timeout=90,
                            write_timeout=180,
                            connect_timeout=30,
                            pool_timeout=30,
                        )

                await _telegram_retry(send_project, attempts=4)

            except asyncio.TimeoutError:
                legacy.logger.exception("CakeStampBot v2.4.5 model worker timeout")

                async def send_model_timeout():
                    return await application.bot.send_message(
                        chat_id=job.chat_id,
                        text="Не получилось собрать модель: превышено время обработки (420 секунд).",
                        reply_markup=legacy.main_menu_keyboard(),
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=20,
                        pool_timeout=20,
                    )

                try:
                    await _telegram_retry(send_model_timeout, attempts=3)
                except Exception:
                    legacy.logger.exception("Could not send model-timeout notice")

            except (TimedOut, NetworkError) as exc:
                # Generation may already be complete. Do not call this a model error.
                legacy.logger.exception("CakeStampBot v2.4.5 Telegram delivery failed")
                if result is not None:
                    text = (
                        "Модель собрана, но Telegram не смог отправить готовый файл после нескольких попыток.\n"
                        "Попробуй создать штамп ещё раз.\n\n"
                        f"Сетевая ошибка: {exc}"
                    )
                else:
                    text = f"Сбой связи с Telegram во время обработки. Попробуй ещё раз.\n\nОшибка: {exc}"

                async def send_network_notice():
                    return await application.bot.send_message(
                        chat_id=job.chat_id,
                        text=text,
                        reply_markup=legacy.main_menu_keyboard(),
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=20,
                        pool_timeout=20,
                    )

                try:
                    await _telegram_retry(send_network_notice, attempts=3)
                except Exception:
                    legacy.logger.exception("Could not send Telegram network-failure notice")

            except Exception as exc:
                legacy.logger.exception("CakeStampBot v2.4.5 model build failed")

                async def send_failure():
                    return await application.bot.send_message(
                        chat_id=job.chat_id,
                        text=f"Не получилось собрать модель.\n\nОшибка: {exc}",
                        reply_markup=legacy.main_menu_keyboard(),
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=20,
                        pool_timeout=20,
                    )

                try:
                    await _telegram_retry(send_failure, attempts=3)
                except Exception:
                    legacy.logger.exception("Could not send build-failure notice")
            finally:
                qq.task_done()

    legacy.cake_worker = cake_worker_v245
