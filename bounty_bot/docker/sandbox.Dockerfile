# Dockerfile for isolated test sandbox
# Multi-language support for Python, TypeScript, JavaScript

FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Default entrypoint for pytest
ENTRYPOINT ["pytest"]
CMD ["--tb=short", "-v"]
