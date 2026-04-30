FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    tcpdump \
    net-tools \
    iputils-ping \
    iproute2 \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .

# Create necessary directories
RUN mkdir -p /app/configs /app/netinstall /app/routeros

# Expose ports
EXPOSE 5001
EXPOSE 67/udp

# Run the application with Gunicorn (single worker to avoid duplicate listeners)
CMD ["/bin/sh", "-c", "gunicorn -w 1 -b 0.0.0.0:${API_PORT:-5001} server:app"]
