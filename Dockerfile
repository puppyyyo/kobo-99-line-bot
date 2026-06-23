# Playwright 官方 image 已內建 Chromium + 所有系統相依
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV TZ=Asia/Taipei \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# data/ 與 logs/ 由 compose 掛 volume 進來
CMD ["python", "-m", "src.main"]
