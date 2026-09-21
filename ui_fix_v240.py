"""CakeStampBot v2.4.0 compact ReplyKeyboard UI fixes.

Keeps only the current stamp settings panel and removes transient ReplyKeyboard
selection messages so font/size/path choices do not fill the Telegram chat.
"""


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
        # These are transient ReplyKeyboard selections. The resulting current
        # settings panel is enough feedback, so remove the user's button message.
        clean = d.get("mode") == "stamp" and (
            text in {
                "❤️ Сердце", "👑 Корона", "✨ Без дополнений",
                "📏 60 мм", "📏 105 мм", "📏 145 мм",
                "⭕ Круг", "▭ Прямоугольник",
                "🔤 Classic", "🔤 Comic", "🔤 GOST",
                "↕️ 10 мм", "↕️ 12 мм", "↕️ 14 мм", "↕️ 16 мм",
                "↔️ Обычный", "⬆️ Сверху", "⬇️ Снизу", "⭕ По окружности",
                "🧩 Отдельно", "🔗 Собрать",
            }
        )
        try:
            return await original_text_router(u, c)
        finally:
            if clean and u.message:
                await _delete_message(u.message)

    app.text_router = compact_text_router
