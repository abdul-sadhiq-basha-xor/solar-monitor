FROM apache/airflow:2.9.3-python3.11

# Switch to root to install system dependencies
USER root

# Install dependencies for Python, Postgres, and kubectl
RUN apt-get update && apt-get install -y \
        libpq-dev \
        gcc \
        curl \
        apt-transport-https \
        ca-certificates \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user
USER airflow

# Copy Python dependencies and install
COPY requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt

# Copy your project code
COPY . /opt/airflow/solar_monitor
WORKDIR /opt/airflow/solar_monitor

ENV DJANGO_SETTINGS_MODULE=solar_monitor.settings
ENV PYTHONPATH=/opt/airflow/solar_monitor