FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port 9000
EXPOSE 9000

# Environment variables
ENV PORT=9000
ENV PYTHONUNBUFFERED=1

# Command to run application
CMD ["python", "deploy_api.py"]
