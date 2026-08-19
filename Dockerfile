FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m botuser
COPY . .
RUN mkdir -p data && chown -R botuser:botuser /app
USER botuser
CMD ["python", "main.py"]
