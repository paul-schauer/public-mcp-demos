FROM python:3.11-slim

# Set a working directory
WORKDIR /app

# Install system dependencies needed for RDKit and other Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	curl \
	libxrender1 \
	libxext6 \
	libsm6 \
	libxrender-dev \
	libgomp1 \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose the default port used by the adapter
EXPOSE 8000

# Default command: run the FastAPI adapter with uvicorn (bind to $PORT or 8000)
CMD ["sh", "-c", "uvicorn adapter_http:api --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 120"]