FROM python:3.12-slim
RUN pip install --no-cache-dir tzdata==2025.2
WORKDIR /app
COPY berechnung.py sensor.py app.py ./
COPY data/ ./data/
COPY dashboard/index.html ./dashboard/
COPY dashboard/vendor/ ./dashboard/vendor/
ENV PYTHONUNBUFFERED=1 HEIZOEL_DATEN=/data TZ=Europe/Berlin
EXPOSE 8080
CMD ["python", "app.py"]
