# Use a more secure base image with minimal attack surface
FROM debian:bookworm-slim AS build-env

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV COLLABHUB_ENVIRONMENT=production
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install Python and critical security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    libpq-dev \
    git \
    curl \
    && apt-get upgrade -y \
    && apt-get dist-upgrade -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies in the virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Create media directory
RUN mkdir -p media

# Create a non-root user for the final image
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Multi-stage build to minimize image size and attack surface
FROM debian:bookworm-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV COLLABHUB_ENVIRONMENT=production
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:$PATH"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    libpq5 \
    ca-certificates \
    && apt-get upgrade -y \
    && apt-get dist-upgrade -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from build stage
COPY --from=build-env /opt/venv /opt/venv

# Copy user from build stage
COPY --from=build-env /etc/passwd /etc/passwd
COPY --from=build-env /etc/group /etc/group

# Set working directory
WORKDIR /app

# Copy only necessary project files
COPY manage.py .
COPY collabhub/ collabhub/
COPY users/ users/
COPY workspace/ workspace/
COPY search/ search/
COPY templates/ templates/
COPY static/ static/

# Create necessary directories
RUN mkdir -p media staticfiles
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Collect static files
RUN python manage.py collectstatic --noinput --settings=collabhub.settings_prod

# Expose port for web server
EXPOSE 8000

# Security hardening
ENV PYTHONHASHSEED=random
ENV PYTHONWARNINGS=default

# Runtime command
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "4", "--timeout", "120", "--worker-class", "uvicorn.workers.UvicornWorker", "collabhub.asgi:application"]