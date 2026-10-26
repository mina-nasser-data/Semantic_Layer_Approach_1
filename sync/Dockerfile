FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sync.py semantic_views.py ./
CMD ["python", "sync.py", "/semantic"]
