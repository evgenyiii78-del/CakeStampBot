# CakeStampBot v0.8.0

Чистая версия проекта.

## Что изменилось

- Вырубка полностью удалена.
- Остались только два режима: 🍰 **Штамп** и 🎂 **Топпер**.
- Логика разделена на отдельные движки:
  - `engine/stamp_engine.py`
  - `engine/topper_engine.py`
  - `engine/common.py`
- Топпер теперь строится правильно:
  - текст отдельным объектом;
  - подложка под буквами, чтобы надпись была единой;
  - одна или две ножки;
  - авто-выбор двух ножек для широких топперов;
  - выбор высоты текста;
  - выбор толщины подложки под буквами.

## Запуск Windows CMD

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
.venv\Scripts\python.exe scripts\smoke_test.py
.venv\Scripts\python.exe bot.py
```

## Docker / Bothost

В Dockerfile уже есть установка шрифтов:

```dockerfile
fonts-dejavu-core
fontconfig
```

На хостинге нужно добавить только:

```env
BOT_TOKEN=...
```

Проверка:

```bash
python scripts/smoke_test.py
```
