FROM python:3.11-slim

# Set a working directory
WORKDIR /app

# Install system dependencies needed for building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	curl \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose the default port used by the adapter
EXPOSE 8000

# Default command: run the FastAPI adapter with uvicorn
CMD ["uvicorn", "adapter_http:api", "--host", "0.0.0.0", "--port", "${PORT:-8000}", "--timeout-keep-alive", "120"]