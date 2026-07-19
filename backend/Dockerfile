# Get static ffmpeg binaries from a pre-built static-ffmpeg image
FROM mwader/static-ffmpeg:6.1.1 AS ffmpeg-source

# Base python image
FROM python:3.11-slim

# Prevent python writing .pyc files & buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy static FFmpeg binaries (runs in less than 1 second!)
COPY --from=ffmpeg-source /ffmpeg /usr/local/bin/
COPY --from=ffmpeg-source /ffprobe /usr/local/bin/

# Set working directory
WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY app/ ./app/

# Create empty cookies.txt in case it is not provided
RUN touch cookies.txt

# Expose port
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
