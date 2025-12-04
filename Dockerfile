
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app


RUN mkdir -p $APP_HOME /frontend

WORKDIR $APP_HOME


RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc libffi-dev git && \
    rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY app.py config.py create_vector_index.py vector_embedding_service.py ./


COPY backend backend
COPY data data
COPY database database
COPY models models
COPY questions questions
COPY routes routes
COPY services services


COPY frontend /app/frontend
COPY frontend /frontend


RUN useradd -m -s /bin/bash appuser \
 && chown -R appuser:appuser $APP_HOME /frontend

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --threads 4 --timeout 120"]