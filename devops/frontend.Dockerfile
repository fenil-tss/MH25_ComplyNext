# Use official Python image
FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src /app

# Expose Streamlit port
EXPOSE 8501

# Streamlit entry command
CMD ["streamlit", "run", "frontend/server.py", "--server.port=8501", "--server.address=0.0.0.0"]
