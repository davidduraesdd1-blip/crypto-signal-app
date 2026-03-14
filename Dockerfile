# Crypto Signal Model — Streamlit + FastAPI
FROM python:3.11-slim

# System dependencies needed by some Python packages (e.g. reportlab, ccxt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Layer-cached dependency install ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application source ---
COPY *.py ./

# Copy Streamlit theme config if present
COPY .streamlit/ .streamlit/

# Runtime ports
#   8501 — Streamlit UI
#   8000 — FastAPI / uvicorn REST server
EXPOSE 8501 8000

# Streamlit default (override in docker-compose for the API service)
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
