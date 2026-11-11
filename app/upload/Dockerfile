FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY app/upload/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/expense_audit ./expense_audit
COPY app/upload/main.py ./main.py
COPY app/upload/templates ./templates
COPY app/upload/static ./static

EXPOSE 8080

CMD ["python", "main.py"]
