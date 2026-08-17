FROM python:3.11-slim

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes, so
# editing application code does not reinstall torch every build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image. Without this the container downloads
# it on first request, which makes the first search look broken.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"

COPY rag/ ./rag/
COPY app.py cli.py ./

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
