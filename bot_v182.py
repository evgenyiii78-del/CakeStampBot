"""CakeStampBot v1.8.2 Compact UI.
UI-only wrapper over the stable bot/engine. Stamp geometry and topper are untouched.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import bot as legacy


def compact_keyboard(c):
    legacy.ensure_stamp_defaults(c)
    d = c.user_data
    path = {"normal":"Обычный","top":"Сверху","bottom":"Снизу","full":"По окружности"}.get(d.get("text_path"), "Обычный")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔵 Диаметр · {d.get('base_size','105')} мм", callback_data="qcat:size"),
         InlineKeyboardButton(f"🔤 Шрифт · {legacy.stamp_font_name(c)}", callback_data="qcat:font")],
        [InlineKeyboardButton(f"↕️ Размер · {float(d.get('text_size_mm',7)):g} мм", callback_data="qcat:h"),
         InlineKeyboardButton(f"〰️ {path}", callback_data="qcat:path")],
        [InlineKeyboardButton(f"❤️ Сердце · {'Да' if d.get('add_heart') else 'Нет'}", callback_data="qs:heart"),
         InlineKeyboardButton(f"🧩 3MF · {'Собрать' if d.get('layout_mode')=='assembled' else 'Отдельно'}", callback_data="qs:layout")],
        [InlineKeyboardButton("🚀 СОЗДАТЬ 3MF", callback_data="create")],
        [InlineKeyboardButton("↩️ Назад в меню", callback_data="restart")],
    ])


def category_keyboard(c, kind):
    legacy.ensure_stamp_defaults(c)
    d = c.user_data
    back = [InlineKeyboardButton("↩️ К настройкам", callback_data="qcat:back")]
    if kind == "size":
        cur = str(d.get("base_size","105"))
        vals = ["60","80","105","130","145"]
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(("✓ " if cur==v else "")+v+" мм", callback_data=f"qs:size:{v}") for v in vals[:3]],
            [InlineKeyboardButton(("✓ " if cur==v else "")+v+" мм", callback_data=f"qs:size:{v}") for v in vals[3:]], back])
    if kind == "h":
        cur = float(d.get("text_size_mm",7)); vals = [5,6,7,8,9,10]
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(("✓ " if cur==v else "")+f"{v} мм", callback_data=f"qs:h:{v}") for v in vals[:3]],
            [InlineKeyboardButton(("✓ " if cur==v else "")+f"{v} мм", callback_data=f"qs:h:{v}") for v in vals[3:]], back])
    if kind == "font":
        cur = d.get("font_choice","classic")
        vals = [("classic","Classic"),("comic","Comic"),("gost","GOST")]
        return InlineKeyboardMarkup([[InlineKeyboardButton(("✓ " if cur==v else "")+name, callback_data=f"qs:font:{v}") for v,name in vals], back])
    cur = d.get("text_path","normal")
    vals = [("normal","Обычный"),("top","Сверху"),("bottom","Снизу"),("full","По окружности")]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(("✓ " if cur==v else "")+name, callback_data=f"qs:path:{v}") for v,name in vals[:2]],
        [InlineKeyboardButton(("✓ " if cur==v else "")+name, callback_data=f"qs:path:{v}") for v,name in vals[2:]], back])


legacy.stamp_quick_keyboard = compact_keyboard
_original_callback = legacy.on_callback


async def compact_callback(update, context):
    q = update.callback_query
    data = q.data or ""
    if data.startswith("qcat:"):
        await q.answer()
        kind = data.split(":",1)[1]
        if kind == "back":
            return await legacy.show_stamp_settings(q, context)
        titles = {"size":"🔵 Выберите диаметр", "font":"🔤 Выберите шрифт", "h":"↕️ Выберите высоту текста", "path":"〰️ Выберите расположение текста"}
        return await q.edit_message_text(titles.get(kind,"Настройка"), reply_markup=category_keyboard(context, kind))
    return await _original_callback(update, context)


legacy.on_callback = compact_callback


async def start_v182(update, context):
    context.user_data.clear()
    await update.message.reply_text("CakeStampBot v1.8.2", reply_markup=legacy.main_menu_keyboard())
    await update.message.reply_text("Выбери режим:", reply_markup=legacy.mode_inline_keyboard())


async def help_v182(update, context):
    await update.message.reply_text("Помощь CakeStampBot v1.8.2\n\n🍰 Штамп: компактные быстрые настройки после ввода текста.\n🎂 Топпер: без изменений.", reply_markup=legacy.main_menu_keyboard())


legacy.start = start_v182
legacy.help_cmd = help_v182

if __name__ == "__main__":
    legacy.main()
