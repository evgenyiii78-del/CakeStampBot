# CakeStampBot v1.0.0 Core Rewrite

Это первая версия нового геометрического ядра.

## Главное изменение

Для топперов текст теперь строится не через пиксельную маску и skeleton, а через **настоящие векторные контуры TTF-шрифта**:

```text
TTF glyph outlines → Shapely polygons → clean extrusion → 3MF
```

Это должно дать:

- более плавные буквы;
- меньше рваных контуров;
- подложку, которая повторяет форму букв;
- ножку/ножки 3 мм без Т-образной базы;
- более чистую геометрию для Bambu Studio / OrcaSlicer.

## Режимы

Оставлены только:

- 🍰 Штамп
- 🎂 Топпер

Вырубка удалена.

## Структура

```text
engine/
├── common.py
├── vector_text.py       # новый векторный TTF core
├── topper_engine.py     # Topper Engine v1
├── stamp_engine.py
└── geometry_checks.py
```

## Топпер v1

3MF содержит два объекта:

```text
Topper_Base
Topper_Text
```

`Topper_Base`:

- подложка по форме букв;
- чуть шире самих букв;
- минимальные плавные перемычки между отдельными островками;
- ножка 3 мм, не Т-образная.

`Topper_Text`:

- реальные векторные буквы;
- слегка утоплены в базу на 0.2 мм.

## Зависимости

Добавлен пакет:

```text
fonttools==4.53.1
```

## Docker / Bothost

Dockerfile уже ставит системные DejaVu-шрифты:

```dockerfile
fonts-dejavu-core
fontconfig
```

На Bothost нужна переменная:

```env
BOT_TOKEN=...
```

## Проверка

```bash
python scripts/smoke_test.py
```

Ожидаемый результат:

```text
Smoke test PASS v1.0.0
```
