"""CakeStampBot v2.4.3 UI/runtime patch for selectable single-line TTF stamps."""
from telegram import ReplyKeyboardMarkup

_WIDTHS = {
    "✏️ 0.35 мм": 0.35,
    "✏️ 0.40 мм": 0.40,
    "✏️ 0.45 мм": 0.45,
    "✏️ 0.60 мм": 0.60,
}


def apply_fixes(app):
    legacy = app.legacy
    original_defaults = legacy.ensure_stamp_defaults

    def defaults_v243(c):
        original_defaults(c)
        d = c.user_data
        try:
            w = round(float(d.get("line_width", 0.45)), 2)
        except Exception:
            w = 0.45
        if w not in {0.35, 0.40, 0.45, 0.60}:
            w = 0.45
        d["line_width"] = w

    legacy.ensure_stamp_defaults = defaults_v243

    def stamp_kb_v243():
        return ReplyKeyboardMarkup(
            [
                ["❤️ Сердце", "👑 Корона", "✨ Без дополнений"],
                ["📏 60 мм", "📏 105 мм", "📏 145 мм"],
                ["⭕ Круг", "▭ Прямоугольник"],
                ["🔤 Classic", "🔤 Comic", "🔤 GOST"],
                ["✏️ 0.35 мм", "✏️ 0.40 мм", "✏️ 0.45 мм", "✏️ 0.60 мм"],
                ["↕️ 10 мм", "↕️ 12 мм", "↕️ 14 мм", "↕️ 16 мм"],
                ["↔️ Обычный", "⬆️ Сверху", "⬇️ Снизу", "⭕ По окружности"],
                ["🧩 Отдельно", "🔗 Собрать"],
                ["✅ СОЗДАТЬ ШТАМП"],
                ["↩️ Главное меню"],
            ],
            resize_keyboard=True,
        )

    app.stamp_kb = stamp_kb_v243
    original_panel = app.panel_text

    def panel_text_v243(c):
        defaults_v243(c)
        text = original_panel(c)
        d = c.user_data
        width = float(d.get("line_width", 0.45))
        choice = str(d.get("font_choice", "classic")).lower()
        if d.get("source") == "image":
            line = f"✏️ Линия изображения: {width:.2f} мм"
        elif choice in {"comic", "gost"}:
            line = f"✏️ Осевая линия TTF: {width:.2f} мм"
        else:
            line = f"✏️ Линия: {width:.2f} мм"
        return text.replace("✏️ Линия: 0.25 мм", line)

    app.panel_text = panel_text_v243
    original_router = app.text_router

    async def text_router_v243(u, c):
        text = (u.message.text or "").strip() if u.message else ""
        if c.user_data.get("mode") == "stamp" and text in _WIDTHS:
            defaults_v243(c)
            c.user_data["line_width"] = _WIDTHS[text]
            c.user_data["step"] = "settings"
            try:
                return await app.show(u.message, c)
            finally:
                try:
                    await u.message.delete()
                except Exception:
                    pass
        return await original_router(u, c)

    app.text_router = text_router_v243
    original_build_model = legacy.build_model

    def build_model_v243(p):
        if p.get("mode") != "stamp":
            return original_build_model(p)

        out = legacy.OUTPUT_DIR / legacy.uuid.uuid4().hex[:10]
        width = float(p.get("line_width", 0.45))

        if p.get("source", "text") == "image":
            return legacy.build_stamp_from_image(
                image_path=p["image_path"],
                output_dir=str(out),
                base_size=p.get("base_size", "105"),
                base_shape=p.get("base_shape", "round"),
                line_width=width,
                add_heart=bool(p.get("add_heart", False)),
                layout_mode=p.get("layout_mode", "assembled"),
            )

        return legacy.build_stamp_from_text(
            text=p["text"],
            output_dir=str(out),
            base_size=p.get("base_size", "105"),
            base_shape=p.get("base_shape", "round"),
            line_width=width,
            font_choice=p.get("font_choice", "classic"),
            text_path=p.get("text_path", "normal"),
            text_size_mm=float(p.get("text_size_mm", 12)),
            add_heart=bool(p.get("add_heart", False)),
            add_crown=bool(p.get("add_crown", False)),
            layout_mode=p.get("layout_mode", "assembled"),
        )

    legacy.build_model = build_model_v243
