# Fonts

В репозитории используются следующие шрифты:
- `DejaVuSerif.ttf` — Classic;
- `Comic Sans MS.ttf` — Comic;
- `GOST type A.ttf` — GOST.

Docker использует файлы напрямую из папки `fonts/`:
- `CAKESTAMP_FONT_COMIC="/usr/src/app/fonts/Comic Sans MS.ttf"`
- `CAKESTAMP_FONT_GOST="/usr/src/app/fonts/GOST type A.ttf"`

Для Comic и GOST fallback на DejaVu отключён: если нужный TTF отсутствует, движок вернёт явную ошибку.
