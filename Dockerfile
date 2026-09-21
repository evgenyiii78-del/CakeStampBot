FROM python:3.11-slim

WORKDIR /usr/src/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       blender \
       fonts-dejavu-core \
       fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && command -v blender \
    && fc-cache -f \
    && blender --version | head -n 1

ENV CAKESTAMP_FONT_CLASSIC=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf
ENV CAKESTAMP_FONT_HAND="/usr/src/app/fonts/Bad Script.ttf"
ENV CAKESTAMP_FONT_COMIC="/usr/src/app/fonts/Bad Script.ttf"
ENV CAKESTAMP_FONT_GOST="/usr/src/app/fonts/GOST type A.ttf"
ENV DATA_DIR=/app/data
ENV STAMP_TEXT_ENGINE=auto
ENV BLENDER_BIN=/usr/bin/blender
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -c "import telegram; print('python-telegram-bot:', telegram.__version__)"

COPY . .

RUN test -f "/usr/src/app/fonts/Bad Script.ttf" \
    && test -f "/usr/src/app/fonts/GOST type A.ttf" \
    && fc-scan "/usr/src/app/fonts/Bad Script.ttf" >/dev/null \
    && fc-scan "/usr/src/app/fonts/GOST type A.ttf" >/dev/null

RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data
CMD ["python", "bot_v236.py"]
