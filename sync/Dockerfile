FROM python:3.12-slim
RUN pip install --no-cache-dir requests==2.32.3 PyYAML==6.0.2
COPY sync.py .
CMD ["python", "-u", "sync.py", "/semantic", "/semantic_views"]
