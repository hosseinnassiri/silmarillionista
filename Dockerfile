FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY main.py ./
COPY data/processed/chroma_db/ ./data/processed/chroma_db/
COPY data/processed/illustrations/ ./data/processed/illustrations/

RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
