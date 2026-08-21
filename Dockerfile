FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fontconfig && rm -rf /var/lib/apt/lists/*
ENV CAKESTAMP_FONT_CLASSIC=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf
ENV CAKESTAMP_FONT_COMIC=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
ENV CAKESTAMP_FONT_GOST=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
ENV DATA_DIR=/app/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data
CMD ["python", "bot.py"]
