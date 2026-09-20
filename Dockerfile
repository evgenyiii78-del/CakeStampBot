FROM python:3.11-slim

# Keep application code outside /app because Bothost may mount /app at runtime.
WORKDIR /usr/src/app

# Blender is required by the primary text-stamp engine and crown generation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       blender \
       fonts-dejavu-core \
       fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && command -v blender \
    && blender --version | head -n 1

ENV CAKESTAMP_FONT_CLASSIC=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf
ENV CAKESTAMP_FONT_COMIC=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
ENV CAKESTAMP_FONT_GOST=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
ENV DATA_DIR=/app/data
ENV STAMP_TEXT_ENGINE=auto
ENV BLENDER_BIN=/usr/bin/blender
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent user data remains in Bothost's /app/data volume.
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data

CMD ["python", "bot_v182.py"]
