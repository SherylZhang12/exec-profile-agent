FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake Chroma's local embedding model into the image so the first request isn't a cold download
RUN python -c "from chromadb.utils import embedding_functions as e; e.DefaultEmbeddingFunction()(['warmup'])"
COPY src ./src
ENV PORT=8080
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT}"]
