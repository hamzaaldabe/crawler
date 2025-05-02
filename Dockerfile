# Use Chrome image as base
FROM selenium/standalone-chrome:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    GOOGLE_CLOUD_PROJECT="modified-math-457111-h4" \
    GCS_BUCKET_NAME="crawler-pdf"

# Switch to root for installation
USER root

# Install Python, pip and PostgreSQL dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    postgresql-client \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && echo "System packages installed successfully"

WORKDIR /app

# Upgrade pip and install wheel
RUN pip3 install --no-cache-dir --upgrade pip wheel setuptools

COPY requirements.txt .

# Install Python packages with verbose output and no cache
RUN pip3 install --no-cache-dir -v --prefer-binary -r requirements.txt \
    && echo "Python packages installed successfully"

COPY . .

# Switch back to seluser (the default user in selenium/standalone-chrome)
USER 1200

EXPOSE 5000

ENV FLASK_APP=run.py \
    FLASK_ENV=production \
    FLASK_DEBUG=0

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "run:app"] 