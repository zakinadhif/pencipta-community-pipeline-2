FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MARIMO_HOME=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 2718

# Shell form agar MARIMO_PASSWORD (dari .env / compose) benar-benar di-expand.
# Marimo membaca --token-password sebagai kata sandi login.
CMD ["sh", "-c", "exec python -m marimo edit 07_live_test.py --host 0.0.0.0 --port 2718 --headless --token-password \"${MARIMO_PASSWORD:-tecnofest}\""]
