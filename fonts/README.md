# Fonts

В репозитории используются следующие шрифты:
- `DejaVuSerif.ttf` — Classic;
- `Bad Script.ttf` — Рукописный;
- `GOST type A.ttf` — GOST.

Docker использует файлы напрямую из папки `fonts/`:
- `CAKESTAMP_FONT_HAND="/usr/src/app/fonts/Bad Script.ttf"`
- `CAKESTAMP_FONT_COMIC="/usr/src/app/fonts/Bad Script.ttf"` — алиас для совместимости со старыми сессиями;
- `CAKESTAMP_FONT_GOST="/usr/src/app/fonts/GOST type A.ttf"`

Для рукописного и GOST fallback на DejaVu отключён: если нужный TTF отсутствует, движок вернёт явную ошибку.
