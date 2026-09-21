FROM python:3.11-slim

WORKDIR /usr/src/app

# Blender is the primary stamp engine. Comic Neue is used as the deployable
# Comic Sans-style font; an explicit Comic Sans MS TTF can override it through
# CAKESTAMP_FONT_COMIC when available.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       blender \
       fonts-dejavu-core \
       fonts-comic-neue \
       fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && command -v blender \
    && fc-cache -f \
    && blender --version | head -n 1

ENV CAKESTAMP_FONT_CLASSIC=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf
ENV CAKESTAMP_FONT_COMIC=/usr/share/fonts/truetype/comic-neue/ComicNeue-Regular.ttf
ENV CAKESTAMP_FONT_GOST=/usr/src/app/fonts/GOST-type-AU.ttf
ENV DATA_DIR=/app/data
ENV STAMP_TEXT_ENGINE=auto
ENV BLENDER_BIN=/usr/bin/blender
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
COPY . .

RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data
CMD ["python", "bot_v182.py"]