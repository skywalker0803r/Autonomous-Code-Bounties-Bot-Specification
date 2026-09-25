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

# pytest is this sandbox's own test runner (the container's test command is
# always supplied explicitly by DockerTester, not baked in here as an
# ENTRYPOINT) - install it directly rather than relying on the target repo's
# requirements.txt to happen to declare it as a dependency, since most won't.
RUN pip install --no-cache-dir pytest

# Set working directory
WORKDIR /app

# Copy application code
COPY . .

# Install dependencies only if the repo actually declares them - not every
# bounty repo is a Python project with a requirements.txt (e.g. a docs/skill
# repo), and an unconditional install would fail the whole build for those.
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
RUN if [ -f package.json ]; then npm install; fi
